import json
from json.decoder import JSONDecodeError
from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.forms.models import inlineformset_factory
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext, ugettext_lazy as _
from django.views.generic import ListView
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import DeleteView
from django_countries.fields import Country

from pretix.api.serializers.item import (
    ItemAddOnSerializer, ItemBundleSerializer, ItemVariationSerializer,
)
from pretix.base.forms import I18nFormSet
from pretix.base.models import (
    CartPosition, Item, ItemCategory, ItemVariation, Order, Question,
    QuestionAnswer, QuestionOption, Quota, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.items import ItemAddOn, ItemBundle
from pretix.base.services.tickets import invalidate_cache
from pretix.base.signals import quota_availability
from pretix.control.forms.item import (
    CategoryForm, ItemAddOnForm, ItemAddOnsFormSet, ItemBundleForm,
    ItemBundleFormSet, ItemCreateForm, ItemUpdateForm, ItemVariationForm,
    ItemVariationsFormSet, QuestionForm, QuestionOptionForm, QuotaForm,
)
from pretix.control.permissions import (
    EventPermissionRequiredMixin, event_permission_required,
)
from pretix.control.signals import item_forms, item_formsets
from pretix.helpers.models import modelcopy

from . import ChartContainingView, CreateView, PaginationMixin, UpdateView


class ItemList(ListView):
    model = Item
    context_object_name = 'items'
    # paginate_by = 30
    # Pagination is disabled as it is very unlikely to be necessary
    # here and could cause problems with the "reorder-within-category" feature
    template_name = 'pretixcontrol/items/index.html'

    def get_queryset(self):
        return Item.objects.filter(
            event=self.request.event
        ).annotate(
            var_count=Count('variations')
        ).prefetch_related("category").order_by(
            'category__position', 'category', 'position'
        )


def item_move(request, item, up=True):
    """
    This is a helper function to avoid duplicating code in item_move_up and
    item_move_down. It takes an item and a direction and then tries to bring
    all items for this category in a new order.
    """
    try:
        item = request.event.items.get(
            id=item
        )
    except Item.DoesNotExist:
        raise Http404(_("The requested product does not exist."))
    items = list(request.event.items.filter(category=item.category).order_by("position"))

    index = items.index(item)
    if index != 0 and up:
        items[index - 1], items[index] = items[index], items[index - 1]
    elif index != len(items) - 1 and not up:
        items[index + 1], items[index] = items[index], items[index + 1]

    for i, item in enumerate(items):
        if item.position != i:
            item.position = i
            item.save()
    messages.success(request, _('The order of items has been updated.'))


@event_permission_required("can_change_items")
def item_move_up(request, organizer, event, item):
    item_move(request, item, up=True)
    return redirect('control:event.items',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


@event_permission_required("can_change_items")
def item_move_down(request, organizer, event, item):
    item_move(request, item, up=False)
    return redirect('control:event.items',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


class CategoryDelete(EventPermissionRequiredMixin, DeleteView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'pretixcontrol/items/category_delete.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_object(self, queryset=None) -> ItemCategory:
        try:
            return self.request.event.categories.get(
                id=self.kwargs['category']
            )
        except ItemCategory.DoesNotExist:
            raise Http404(_("The requested product category does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        for item in self.object.items.all():
            item.category = None
            item.save()
        success_url = self.get_success_url()
        self.object.log_action('pretix.event.category.deleted', user=self.request.user)
        self.object.delete()
        messages.success(request, _('The selected category has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class CategoryUpdate(EventPermissionRequiredMixin, UpdateView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'pretixcontrol/items/category.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_object(self, queryset=None) -> ItemCategory:
        url = resolve(self.request.path_info)
        try:
            return self.request.event.categories.get(
                id=url.kwargs['category']
            )
        except ItemCategory.DoesNotExist:
            raise Http404(_("The requested product category does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.category.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class CategoryCreate(EventPermissionRequiredMixin, CreateView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'pretixcontrol/items/category.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_success_url(self) -> str:
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.categories.get(pk=self.request.GET.get("copy_from"))
            except ItemCategory.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
        else:
            kwargs['instance'] = ItemCategory(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new category has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.category.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class CategoryList(PaginationMixin, ListView):
    model = ItemCategory
    context_object_name = 'categories'
    template_name = 'pretixcontrol/items/categories.html'

    def get_queryset(self):
        return self.request.event.categories.all()


def category_move(request, category, up=True):
    """
    This is a helper function to avoid duplicating code in category_move_up and
    category_move_down. It takes a category and a direction and then tries to bring
    all categories for this event in a new order.
    """
    try:
        category = request.event.categories.get(
            id=category
        )
    except ItemCategory.DoesNotExist:
        raise Http404(_("The requested product category does not exist."))
    categories = list(request.event.categories.order_by("position"))

    index = categories.index(category)
    if index != 0 and up:
        categories[index - 1], categories[index] = categories[index], categories[index - 1]
    elif index != len(categories) - 1 and not up:
        categories[index + 1], categories[index] = categories[index], categories[index + 1]

    for i, cat in enumerate(categories):
        if cat.position != i:
            cat.position = i
            cat.save()
    messages.success(request, _('The order of categories has been updated.'))


@event_permission_required("can_change_items")
def category_move_up(request, organizer, event, category):
    category_move(request, category, up=True)
    return redirect('control:event.items.categories',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


@event_permission_required("can_change_items")
def category_move_down(request, organizer, event, category):
    category_move(request, category, up=False)
    return redirect('control:event.items.categories',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


class QuestionList(PaginationMixin, ListView):
    model = Question
    context_object_name = 'questions'
    template_name = 'pretixcontrol/items/questions.html'

    def get_queryset(self):
        return self.request.event.questions.prefetch_related('items')


@transaction.atomic
@event_permission_required("can_change_items")
def reorder_questions(request, organizer, event):
    try:
        ids = json.loads(request.body.decode('utf-8'))['ids']
    except (JSONDecodeError, KeyError):
        return HttpResponseBadRequest("expected JSON: {ids:[]}")

    questions = request.event.questions.filter(id__in=ids)

    if questions.count() != len(ids):
        raise Http404(_("Some of the provided question ids are invalid."))

    positions = questions.values_list('position', flat=True)

    if positions.last() - positions.first() + 1 != questions.count():
        return HttpResponseBadRequest("ids have to be from a consecutive range")

    for pos, id in zip(positions, ids):
        qt = questions.get(id=id)
        if qt.position != pos:
            qt.position = pos
            qt.save()

    return HttpResponse()


def question_move(request, question, up=True):
    """
    This is a helper function to avoid duplicating code in question_move_up and
    question_move_down. It takes a question and a direction and then tries to bring
    all items for this question in a new order.
    """
    try:
        question = request.event.questions.get(
            id=question
        )
    except Question.DoesNotExist:
        raise Http404(_("The selected question does not exist."))
    questions = list(request.event.questions.order_by("position"))

    index = questions.index(question)
    if index != 0 and up:
        questions[index - 1], questions[index] = questions[index], questions[index - 1]
    elif index != len(questions) - 1 and not up:
        questions[index + 1], questions[index] = questions[index], questions[index + 1]

    for i, qt in enumerate(questions):
        if qt.position != i:
            qt.position = i
            qt.save()
    messages.success(request, _('The order of questions has been updated.'))


@event_permission_required("can_change_items")
def question_move_up(request, organizer, event, question):
    question_move(request, question, up=True)
    return redirect('control:event.items.questions',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


@event_permission_required("can_change_items")
def question_move_down(request, organizer, event, question):
    question_move(request, question, up=False)
    return redirect('control:event.items.questions',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


class QuestionDelete(EventPermissionRequiredMixin, DeleteView):
    model = Question
    template_name = 'pretixcontrol/items/question_delete.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None) -> Question:
        try:
            return self.request.event.questions.get(
                id=self.kwargs['question']
            )
        except Question.DoesNotExist:
            raise Http404(_("The requested question does not exist."))

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = list(self.get_object().items.all())
        return context

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.log_action(action='pretix.event.question.deleted', user=request.user)
        self.object.delete()
        messages.success(request, _('The selected question has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class QuestionMixin:
    @cached_property
    def formset(self):
        formsetclass = inlineformset_factory(
            Question, QuestionOption,
            form=QuestionOptionForm, formset=I18nFormSet,
            can_order=True, can_delete=True, extra=0
        )
        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            queryset=(QuestionOption.objects.filter(question=self.object)
                                      if self.object else QuestionOption.objects.none()),
                            event=self.request.event)

    def save_formset(self, obj):
        if self.formset.is_valid():
            for form in self.formset.initial_forms:
                if form in self.formset.deleted_forms:
                    if not form.instance.pk:
                        continue
                    obj.log_action(
                        'pretix.event.question.option.deleted', user=self.request.user, data={
                            'id': form.instance.pk
                        }
                    )
                    form.instance.delete()
                    form.instance.pk = None

            forms = self.formset.ordered_forms + [
                ef for ef in self.formset.extra_forms
                if ef not in self.formset.ordered_forms and ef not in self.formset.deleted_forms
            ]
            for i, form in enumerate(forms):
                form.instance.position = i
                form.instance.question = obj
                created = not form.instance.pk
                form.save()
                if form.has_changed():
                    change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                    change_data['id'] = form.instance.pk
                    obj.log_action(
                        'pretix.event.question.option.added' if created else
                        'pretix.event.question.option.changed',
                        user=self.request.user, data=change_data
                    )

            return True
        return False

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        return ctx


class QuestionView(EventPermissionRequiredMixin, QuestionMixin, ChartContainingView, DetailView):
    model = Question
    template_name = 'pretixcontrol/items/question.html'
    permission = 'can_change_items'
    template_name_field = 'question'

    def get_answer_statistics(self):
        qs = QuestionAnswer.objects.filter(
            question=self.object, orderposition__isnull=False,
            orderposition__order__event=self.request.event
        )
        if self.request.GET.get("status", "np") != "":
            s = self.request.GET.get("status", "np")
            if s == 'o':
                qs = qs.filter(orderposition__order__status=Order.STATUS_PENDING,
                               orderposition__order__expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'np':
                qs = qs.filter(orderposition__order__status__in=[Order.STATUS_PENDING, Order.STATUS_PAID])
            elif s == 'ne':
                qs = qs.filter(orderposition__order__status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            else:
                qs = qs.filter(orderposition__order__status=s)
        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(orderposition__item_id__in=(i,))

        if self.object.type == Question.TYPE_FILE:
            qs = [
                {
                    'answer': ugettext('File uploaded'),
                    'count': qs.filter(file__isnull=False).count(),
                }
            ]
        elif self.object.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            qs = qs.order_by('options').values('options', 'options__answer') \
                .annotate(count=Count('id')).order_by('-count')
            for a in qs:
                a['alink'] = a['options']
                a['answer'] = str(a['options__answer'])
                del a['options__answer']
        elif self.object.type in (Question.TYPE_TIME, Question.TYPE_DATE, Question.TYPE_DATETIME):
            qs = qs.order_by('answer')
            model_cache = {a.answer: a for a in qs}
            qs = qs.values('answer').annotate(count=Count('id')).order_by('answer')
            for a in qs:
                a['alink'] = a['answer']
                a['answer'] = str(model_cache[a['answer']])
        else:
            qs = qs.order_by('answer').values('answer').annotate(count=Count('id')).order_by('-count')

            if self.object.type == Question.TYPE_BOOLEAN:
                for a in qs:
                    a['alink'] = a['answer']
                    a['answer'] = ugettext('Yes') if a['answer'] == 'True' else ugettext('No')
                    a['answer_bool'] = a['answer'] == 'True'
            elif self.object.type == Question.TYPE_COUNTRYCODE:
                for a in qs:
                    a['alink'] = a['answer']
                    a['answer'] = Country(a['answer']).name or a['answer']

        return list(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['items'] = self.object.items.all()
        stats = self.get_answer_statistics()
        ctx['stats'] = stats
        ctx['stats_json'] = json.dumps(stats)
        return ctx

    def get_object(self, queryset=None) -> Question:
        try:
            return self.request.event.questions.get(
                id=self.kwargs['question']
            )
        except Question.DoesNotExist:
            raise Http404(_("The requested question does not exist."))

    def get_success_url(self) -> str:
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class QuestionUpdate(EventPermissionRequiredMixin, QuestionMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = 'pretixcontrol/items/question_edit.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None) -> Question:
        try:
            return self.request.event.questions.get(
                id=self.kwargs['question']
            )
        except Question.DoesNotExist:
            raise Http404(_("The requested question does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        if form.cleaned_data.get('type') in ('M', 'C'):
            if not self.save_formset(self.get_object()):
                return self.get(self.request, *self.args, **self.kwargs)

        if form.has_changed():
            self.object.log_action(
                'pretix.event.question.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class QuestionCreate(EventPermissionRequiredMixin, QuestionMixin, CreateView):
    model = Question
    form_class = QuestionForm
    template_name = 'pretixcontrol/items/question_edit.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Question(event=self.request.event)
        return kwargs

    def get_success_url(self) -> str:
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_object(self, **kwargs):
        return None

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        if form.cleaned_data.get('type') in ('M', 'C'):
            if not self.formset.is_valid():
                return self.get(self.request, *self.args, **self.kwargs)

        messages.success(self.request, _('The new question has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.question.added', user=self.request.user, data=dict(form.cleaned_data))

        if form.cleaned_data.get('type') in ('M', 'C'):
            self.save_formset(form.instance)

        return ret


class QuotaList(PaginationMixin, ListView):
    model = Quota
    context_object_name = 'quotas'
    template_name = 'pretixcontrol/items/quotas.html'

    def get_queryset(self):
        qs = Quota.objects.filter(
            event=self.request.event
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=Item.objects.annotate(has_variations=Count('variations'))
            ),
            "variations",
            "variations__item"
        )
        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)
        return qs


class QuotaCreate(EventPermissionRequiredMixin, CreateView):
    model = Quota
    form_class = QuotaForm
    template_name = 'pretixcontrol/items/quota_edit.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_success_url(self) -> str:
        return reverse('control:event.items.quotas', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new quota has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.quota.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.quotas.get(pk=self.request.GET.get("copy_from"))
            except Quota.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
            kwargs.setdefault('initial', {})
            kwargs['initial']['itemvars'] = [str(i.pk) for i in self.copy_from.items.all()] + [
                '{}-{}'.format(v.item_id, v.pk) for v in self.copy_from.variations.all()
            ]
        else:
            kwargs['instance'] = Quota(event=self.request.event)
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class QuotaView(ChartContainingView, DetailView):
    model = Quota
    template_name = 'pretixcontrol/items/quota.html'
    context_object_name = 'quota'

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data()

        avail = self.object.availability()
        ctx['avail'] = avail

        data = [
            {
                'label': ugettext('Paid orders'),
                'value': self.object.count_paid_orders(),
                'sum': True,
            },
            {
                'label': ugettext('Pending orders'),
                'value': self.object.count_pending_orders(),
                'sum': True,
            },
            {
                'label': ugettext('Vouchers and waiting list reservations'),
                'value': self.object.count_blocking_vouchers(),
                'sum': True,
            },
            {
                'label': ugettext('Current user\'s carts'),
                'value': self.object.count_in_cart(),
                'sum': True,
            },
        ]

        sum_values = sum([d['value'] for d in data if d['sum']])
        s = self.object.size - sum_values if self.object.size is not None else ugettext('Infinite')

        data.append({
            'label': ugettext('Available quota'),
            'value': s,
            'sum': False,
            'strong': True
        })
        data.append({
            'label': ugettext('Waiting list (pending)'),
            'value': self.object.count_waiting_list_pending(),
            'sum': False,
        })

        if self.object.size is not None:
            data.append({
                'label': ugettext('Currently for sale'),
                'value': avail[1],
                'sum': False,
                'strong': True
            })

        ctx['quota_chart_data'] = json.dumps([r for r in data if r.get('sum')])
        ctx['quota_table_rows'] = list(data)
        ctx['quota_overbooked'] = sum_values - self.object.size if self.object.size is not None else 0

        ctx['has_plugins'] = False
        res = (
            Quota.AVAILABILITY_GONE if self.object.size is not None and self.object.size - sum_values <= 0 else
            Quota.AVAILABILITY_OK,
            self.object.size - sum_values if self.object.size is not None else None
        )
        for recv, resp in quota_availability.send(sender=self.request.event, quota=self.object, result=res,
                                                  count_waitinglist=True):
            if resp != res:
                ctx['has_plugins'] = True

        ctx['has_ignore_vouchers'] = Voucher.objects.filter(
            Q(allow_ignore_quota=True) &
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now())) &
            Q(Q(self.object._position_lookup) | Q(quota=self.object)) &
            Q(redeemed__lt=F('max_usages'))
        ).exists()
        if self.object.closed:
            ctx['closed_and_sold_out'] = self.object._availability(ignore_closed=True)[0] <= Quota.AVAILABILITY_ORDERED

        return ctx

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))

    def post(self, request, *args, **kwargs):
        if not request.user.has_event_permission(request.organizer, request.event, 'can_change_items', request):
            raise PermissionDenied()
        quota = self.get_object()
        if 'reopen' in request.POST:
            quota.closed = False
            quota.save(update_fields=['closed'])
            quota.log_action('pretix.event.quota.opened', user=request.user)
            messages.success(request, _('The quota has been re-opened.'))
        if 'disable' in request.POST:
            quota.closed = False
            quota.close_when_sold_out = False
            quota.save(update_fields=['closed', 'close_when_sold_out'])
            quota.log_action('pretix.event.quota.opened', user=request.user)
            quota.log_action(
                'pretix.event.quota.changed', user=self.request.user, data={
                    'close_when_sold_out': False
                }
            )
            messages.success(request, _('The quota has been re-opened and will not close again.'))
        return redirect(reverse('control:event.items.quotas.show', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'quota': quota.pk
        }))


class QuotaUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Quota
    form_class = QuotaForm
    template_name = 'pretixcontrol/items/quota_edit.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data()
        return ctx

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.quota.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
            if ((form.initial.get('subevent') and not form.instance.subevent) or
                    (form.instance.subevent and form.initial.get('subevent') != form.instance.subevent.pk)):

                if form.initial.get('subevent'):
                    se = SubEvent.objects.get(event=self.request.event, pk=form.initial.get('subevent'))
                    se.log_action(
                        'pretix.subevent.quota.deleted', user=self.request.user, data={
                            'id': form.instance.pk
                        }
                    )
                if form.instance.subevent:
                    form.instance.subevent.log_action(
                        'pretix.subevent.quota.added', user=self.request.user, data={
                            'id': form.instance.pk
                        }
                    )
            form.instance.rebuild_cache()
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.items.quotas.show', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'quota': self.object.pk
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class QuotaDelete(EventPermissionRequiredMixin, DeleteView):
    model = Quota
    template_name = 'pretixcontrol/items/quota_delete.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = list(self.object.items.all())
        context['vouchers'] = self.object.vouchers.count()
        return context

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.log_action(action='pretix.event.quota.deleted', user=request.user)
        self.object.delete()
        messages.success(self.request, _('The selected quota has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.items.quotas', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class ItemDetailMixin(SingleObjectMixin):
    model = Item
    context_object_name = 'item'

    def get_object(self, queryset=None) -> Item:
        try:
            if not hasattr(self, 'object') or not self.object:
                self.item = self.request.event.items.get(
                    id=self.kwargs['item']
                )
                self.object = self.item
            return self.object
        except Item.DoesNotExist:
            raise Http404(_("The requested item does not exist."))


class ItemCreate(EventPermissionRequiredMixin, CreateView):
    form_class = ItemCreateForm
    template_name = 'pretixcontrol/item/create.html'
    permission = 'can_change_items'

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.object.id,
        })

    def get_initial(self):
        initial = super().get_initial()
        trs = list(self.request.event.tax_rules.all())
        if len(trs) == 1:
            initial['tax_rule'] = trs[0]
        return initial

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))

        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.item.added', user=self.request.user, data={
            k: (form.cleaned_data.get(k).name
                if isinstance(form.cleaned_data.get(k), File)
                else form.cleaned_data.get(k))
            for k in form.changed_data
        })
        return ret

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        newinst = Item(event=self.request.event)
        kwargs = super().get_form_kwargs()
        kwargs.update({'instance': newinst, 'user': self.request.user})
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class ItemUpdateGeneral(ItemDetailMixin, EventPermissionRequiredMixin, UpdateView):
    form_class = ItemUpdateForm
    template_name = 'pretixcontrol/item/index.html'
    permission = 'can_change_items'

    @cached_property
    def plugin_forms(self):
        forms = []
        for rec, resp in item_forms.send(sender=self.request.event, item=self.item, request=self.request):
            if isinstance(resp, (list, tuple)):
                forms.extend(resp)
            else:
                forms.append(resp)
        return forms

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    def is_valid(self, form):
        v = (
            form.is_valid()
            and all(f.is_valid() for f in self.plugin_forms)
            and all(f.is_valid() for f in self.formsets.values())
        )
        if v and form.cleaned_data['category'] and form.cleaned_data['category'].is_addon:
            addons = self.formsets['addons'].ordered_forms + [
                ef for ef in self.formsets['addons'].extra_forms
                if ef not in self.formsets['addons'].ordered_forms and ef not in self.formsets['addons'].deleted_forms
            ]
            if addons:
                messages.error(self.request,
                               _('You cannot add add-ons to a product that is only available as an add-on '
                                 'itself.'))
                v = False

            bundles = [
                ef for ef in self.formsets['bundles'].forms
                if ef not in self.formsets['bundles'].deleted_forms
            ]
            if bundles:
                messages.error(self.request,
                               _('You cannot add bundles to a product that is only available as an add-on '
                                 'itself.'))
                v = False
        return v

    def post(self, request, *args, **kwargs):
        self.get_object()
        form = self.get_form()
        if self.is_valid(form):
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def save_formset(self, key, log_base, attr='item', order=True, serializer=None,
                     rm_verb='removed'):
        for form in self.formsets[key].deleted_forms:
            if not form.instance.pk:
                continue
            d = {
                'id': form.instance.pk
            }
            if serializer:
                d.update(serializer(form.instance).data)
            self.get_object().log_action(
                'pretix.event.item.{}.{}'.format(log_base, rm_verb), user=self.request.user, data=d
            )
            form.instance.delete()
            form.instance.pk = None

        if order:
            forms = self.formsets[key].ordered_forms + [
                ef for ef in self.formsets[key].extra_forms
                if ef not in self.formsets[key].ordered_forms and ef not in self.formsets[key].deleted_forms
            ]
        else:
            forms = [
                ef for ef in self.formsets[key].forms
                if ef not in self.formsets[key].deleted_forms
            ]
        for i, form in enumerate(forms):
            if order:
                form.instance.position = i
            setattr(form.instance, attr, self.get_object())
            created = not form.instance.pk
            form.save()
            if form.has_changed() and any(a for a in form.changed_data if a != 'ORDER'):
                change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                if key == 'variations':
                    change_data['value'] = form.instance.value
                change_data['id'] = form.instance.pk
                self.get_object().log_action(
                    'pretix.event.item.{}.changed'.format(log_base) if not created else
                    'pretix.event.item.{}.added'.format(log_base),
                    user=self.request.user, data=change_data
                )

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed() or any(f.has_changed() for f in self.plugin_forms):
            data = {
                k: form.cleaned_data.get(k)
                for k in form.changed_data
            }
            for f in self.plugin_forms:
                data.update({
                    k: (f.cleaned_data.get(k).name
                        if isinstance(f.cleaned_data.get(k), File)
                        else f.cleaned_data.get(k))
                    for k in f.changed_data
                })
            self.object.log_action(
                'pretix.event.item.changed', user=self.request.user, data=data
            )
            invalidate_cache.apply_async(kwargs={'event': self.request.event.pk, 'item': self.object.pk})
        for f in self.plugin_forms:
            f.save()

        for k, v in self.formsets.items():
            if k == 'variations':
                self.save_formset(
                    'variations', 'variation',
                    serializer=ItemVariationSerializer,
                    rm_verb='deleted'
                )
            elif k == 'addons':
                self.save_formset(
                    'addons', 'addons', 'base_item',
                    serializer=ItemAddOnSerializer
                )
            elif k == 'bundles':
                self.save_formset(
                    'bundles', 'bundles', 'base_item', order=False,
                    serializer=ItemBundleSerializer
                )
            else:
                v.save()

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['plugin_forms'] = self.plugin_forms
        ctx['formsets'] = self.formsets

        if not ctx['item'].active and ctx['item'].bundled_with.count() > 0:
            messages.info(self.request, _("You disabled this item, but it is still part of a product bundle. "
                                          "Your participants won't be able to buy the bundle unless you remove this "
                                          "item from it."))

        return ctx

    @cached_property
    def formsets(self):
        f = OrderedDict([
            ('variations', inlineformset_factory(
                Item, ItemVariation,
                form=ItemVariationForm, formset=ItemVariationsFormSet,
                can_order=True, can_delete=True, extra=0
            )(
                self.request.POST if self.request.method == "POST" else None,
                queryset=ItemVariation.objects.filter(item=self.get_object()),
                event=self.request.event, prefix="variations"
            )),
            ('addons', inlineformset_factory(
                Item, ItemAddOn,
                form=ItemAddOnForm, formset=ItemAddOnsFormSet,
                can_order=True, can_delete=True, extra=0
            )(
                self.request.POST if self.request.method == "POST" else None,
                queryset=ItemAddOn.objects.filter(base_item=self.get_object()),
                event=self.request.event, prefix="addons"
            )),
            ('bundles', inlineformset_factory(
                Item, ItemBundle,
                form=ItemBundleForm, formset=ItemBundleFormSet,
                fk_name='base_item',
                can_order=False, can_delete=True, extra=0
            )(
                self.request.POST if self.request.method == "POST" else None,
                queryset=ItemBundle.objects.filter(base_item=self.get_object()),
                event=self.request.event, item=self.item, prefix="bundles"
            )),
        ])
        if not self.object.has_variations:
            del f['variations']

        i = 0
        for rec, resp in item_formsets.send(sender=self.request.event, item=self.item, request=self.request):
            if isinstance(resp, (list, tuple)):
                for k in resp:
                    f['p-{}'.format(i)] = k
                    i += 1
            else:
                f['p-{}'.format(i)] = resp
                i += 1
        return f


class ItemDelete(EventPermissionRequiredMixin, DeleteView):
    model = Item
    template_name = 'pretixcontrol/item/delete.html'
    permission = 'can_change_items'
    context_object_name = 'item'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.is_allowed()
        context['vouchers'] = self.object.vouchers.count()
        return context

    def is_allowed(self) -> bool:
        return not self.get_object().orderposition_set.exists()

    def get_object(self, queryset=None) -> Item:
        if not hasattr(self, 'object') or not self.object:
            try:
                self.object = self.request.event.items.get(
                    id=self.kwargs['item']
                )
            except Item.DoesNotExist:
                raise Http404(_("The requested product does not exist."))
        return self.object

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        o = self.get_object()
        if o.allow_delete():
            CartPosition.objects.filter(addon_to__item=self.get_object()).delete()
            self.get_object().cartposition_set.all().delete()
            self.get_object().log_action('pretix.event.item.deleted', user=self.request.user)
            self.get_object().delete()
            messages.success(request, _('The selected product has been deleted.'))
            return HttpResponseRedirect(success_url)
        else:
            o = self.get_object()
            o.active = False
            o.save()
            o.log_action('pretix.event.item.changed', user=self.request.user, data={
                'active': False
            })
            messages.success(request, _('The selected product has been deactivated.'))
            return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.items', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
