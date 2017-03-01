import json

from django.contrib import messages
from django.core.files import File
from django.core.urlresolvers import resolve, reverse
from django.db import transaction
from django.db.models import Count, F, Q
from django.forms.models import ModelMultipleChoiceField, inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext, ugettext_lazy as _
from django.views.generic import ListView
from django.views.generic.base import TemplateView
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import DeleteView

from pretix.base.forms import I18nFormSet
from pretix.base.models import (
    CachedTicket, Item, ItemCategory, ItemVariation, Order, Question,
    QuestionAnswer, QuestionOption, Quota, Voucher,
)
from pretix.base.models.items import ItemAddOn
from pretix.control.forms.item import (
    CategoryForm, ItemAddOnForm, ItemAddOnsFormSet, ItemCreateForm,
    ItemUpdateForm, ItemVariationForm, ItemVariationsFormSet, QuestionForm,
    QuestionOptionForm, QuotaForm,
)
from pretix.control.permissions import (
    EventPermissionRequiredMixin, event_permission_required,
)

from . import ChartContainingView, CreateView, UpdateView


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
        ).prefetch_related("category")


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
    messages.success(request, _('The order of items as been updated.'))


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


class CategoryList(ListView):
    model = ItemCategory
    context_object_name = 'categories'
    paginate_by = 30
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


class QuestionList(ListView):
    model = Question
    context_object_name = 'questions'
    paginate_by = 30
    template_name = 'pretixcontrol/items/questions.html'

    def get_queryset(self):
        return self.request.event.questions.all()


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
            can_order=False, can_delete=True, extra=0
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
                elif form.has_changed():
                    form.instance.question = obj
                    form.save()
                    change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                    change_data['id'] = form.instance.pk
                    obj.log_action(
                        'pretix.event.question.option.changed',
                        user=self.request.user, data=change_data
                    )

            for form in self.formset.extra_forms:
                if not form.has_changed():
                    continue
                if self.formset._should_delete_form(form):
                    continue
                form.instance.question = obj
                form.save()
                change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                change_data['id'] = form.instance.pk
                obj.log_action(
                    'pretix.event.question.option.added',
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
        if self.request.GET.get("status", "") != "":
            s = self.request.GET.get("status", "")
            if s == 'o':
                qs = qs.filter(orderposition__order__status=Order.STATUS_PENDING,
                               expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'ne':
                qs = qs.filter(orderposition__order__status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            else:
                qs = qs.filter(orderposition__order__status=s)
        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(orderposition__item_id__in=(i,))

        if self.object.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
            qs = qs.order_by('options').values('options', 'options__answer')\
                   .annotate(count=Count('id')).order_by('-count')
            for a in qs:
                a['answer'] = str(a['options__answer'])
                del a['options__answer']
        else:
            qs = qs.order_by('answer').values('answer').annotate(count=Count('id')).order_by('-count')

            if self.object.type == Question.TYPE_BOOLEAN:
                for a in qs:
                    a['answer'] = ugettext('Yes') if a['answer'] == 'True' else ugettext('No')
                    a['answer_bool'] = a['answer'] == 'True'

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


class QuotaList(ListView):
    model = Quota
    context_object_name = 'quotas'
    paginate_by = 30
    template_name = 'pretixcontrol/items/quotas.html'

    def get_queryset(self):
        return Quota.objects.filter(
            event=self.request.event
        ).prefetch_related("items")


class QuotaEditorMixin:
    @cached_property
    def items(self) -> "List[Item]":
        return list(self.request.event.items.all().prefetch_related("variations"))

    def get_form(self, form_class=QuotaForm):
        if not hasattr(self, '_form'):
            kwargs = self.get_form_kwargs()
            kwargs['items'] = self.items
            self._form = form_class(**kwargs)
        return self._form

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['items'] = self.items
        for item in context['items']:
            item.field = self.get_form(QuotaForm)['item_%s' % item.id]
        return context

    @transaction.atomic
    def form_valid(self, form):
        res = super().form_valid(form)
        items = self.object.items.all()
        variations = self.object.variations.all()
        selected_variations = []
        self.object = form.instance
        for item in self.items:
            field = form.fields['item_%s' % item.id]
            data = form.cleaned_data['item_%s' % item.id]
            if isinstance(field, ModelMultipleChoiceField):
                for v in data:
                    selected_variations.append(v)
            if data and item not in items:
                self.object.items.add(item)
            elif not data and item in items:
                self.object.items.remove(item)

        self.object.variations.add(*[v for v in selected_variations if v not in variations])
        self.object.variations.remove(*[v for v in variations if v not in selected_variations])
        return res


class QuotaCreate(EventPermissionRequiredMixin, QuotaEditorMixin, CreateView):
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
                'label': ugettext('Vouchers'),
                'value': self.object.count_blocking_vouchers(),
                'sum': True,
            },
            {
                'label': ugettext('Current user\'s carts'),
                'value': self.object.count_in_cart(),
                'sum': True,
            },
            {
                'label': ugettext('Waiting list'),
                'value': self.object.count_waiting_list_pending(),
                'sum': False,
            },
        ]
        ctx['quota_table_rows'] = list(data)

        sum_values = sum([d['value'] for d in data if d['sum']])

        if self.object.size is not None:
            data.append({
                'label': ugettext('Current availability'),
                'value': avail[1]
            })

        ctx['quota_chart_data'] = json.dumps(data)
        ctx['quota_overbooked'] = sum_values - self.object.size if self.object.size is not None else 0

        ctx['has_ignore_vouchers'] = Voucher.objects.filter(
            Q(allow_ignore_quota=True) &
            Q(Q(valid_until__isnull=True) | Q(valid_until__gte=now())) &
            Q(Q(self.object._position_lookup) | Q(quota=self.object)) &
            Q(redeemed__lt=F('max_usages'))
        ).exists()

        return ctx

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))


class QuotaUpdate(EventPermissionRequiredMixin, QuotaEditorMixin, UpdateView):
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
        context['dependent'] = list(self.get_object().items.all())
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

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.cleaned_data['copy_from']:
            form.instance.category = form.cleaned_data['copy_from'].category
            form.instance.description = form.cleaned_data['copy_from'].description
            form.instance.active = form.cleaned_data['copy_from'].active
            form.instance.available_from = form.cleaned_data['copy_from'].available_from
            form.instance.available_until = form.cleaned_data['copy_from'].available_until
            form.instance.require_voucher = form.cleaned_data['copy_from'].require_voucher
            form.instance.hide_without_voucher = form.cleaned_data['copy_from'].hide_without_voucher
            form.instance.allow_cancel = form.cleaned_data['copy_from'].allow_cancel

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
        kwargs.update({'instance': newinst})
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class ItemUpdateGeneral(ItemDetailMixin, EventPermissionRequiredMixin, UpdateView):
    form_class = ItemUpdateForm
    template_name = 'pretixcontrol/item/index.html'
    permission = 'can_change_items'

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.item.changed', user=self.request.user, data={
                    k: (form.cleaned_data.get(k).name
                        if isinstance(form.cleaned_data.get(k), File)
                        else form.cleaned_data.get(k))
                    for k in form.changed_data
                }
            )
            CachedTicket.objects.filter(order_position__item=self.item).delete()
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class ItemVariations(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_items'
    template_name = 'pretixcontrol/item/variations.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = None

    @cached_property
    def formset(self):
        formsetclass = inlineformset_factory(
            Item, ItemVariation,
            form=ItemVariationForm, formset=ItemVariationsFormSet,
            can_order=True, can_delete=True, extra=0
        )
        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            queryset=ItemVariation.objects.filter(item=self.get_object()),
                            event=self.request.event)

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            if self.formset.is_valid():
                for form in self.formset.deleted_forms:
                    if not form.instance.pk:
                        continue
                    self.get_object().log_action(
                        'pretix.event.item.variation.deleted', user=self.request.user, data={
                            'value': form.instance.value,
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
                    form.instance.item = self.get_object()
                    created = not form.instance.pk
                    form.save()
                    if form.has_changed():
                        change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                        change_data['value'] = form.instance.value
                        change_data['id'] = form.instance.pk
                        self.get_object().log_action(
                            'pretix.event.item.variation.changed' if not created else
                            'pretix.event.item.variation.added',
                            user=self.request.user, data=change_data
                        )

                messages.success(self.request, _('Your changes have been saved.'))
                return redirect(self.get_success_url())
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return self.get(request, *args, **kwargs)

    def get_success_url(self) -> str:
        return reverse('control:event.item.variations', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    def get_context_data(self, **kwargs) -> dict:
        self.object = self.get_object()
        context = super().get_context_data(**kwargs)
        context['formset'] = self.formset
        return context


class ItemAddOns(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_items'
    template_name = 'pretixcontrol/item/addons.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = None

    @cached_property
    def formset(self):
        formsetclass = inlineformset_factory(
            Item, ItemAddOn,
            form=ItemAddOnForm, formset=ItemAddOnsFormSet,
            can_order=False, can_delete=True, extra=0
        )
        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            queryset=ItemAddOn.objects.filter(base_item=self.get_object()),
                            event=self.request.event)

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            if self.formset.is_valid():
                for form in self.formset.deleted_forms:
                    if not form.instance.pk:
                        continue
                    self.get_object().log_action(
                        'pretix.event.item.addons.removed', user=self.request.user, data={
                            'category': form.instance.addon_category.pk
                        }
                    )
                    form.instance.delete()
                    form.instance.pk = None

                forms = [
                    ef for ef in self.formset.extra_forms + self.formset.initial_forms
                    if ef not in self.formset.deleted_forms
                ]
                for i, form in enumerate(forms):
                    form.instance.base_item = self.get_object()
                    created = not form.instance.pk
                    form.save()
                    if form.has_changed():
                        change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                        change_data['id'] = form.instance.pk
                        self.get_object().log_action(
                            'pretix.event.item.addons.changed' if not created else
                            'pretix.event.item.addons.added',
                            user=self.request.user, data=change_data
                        )

                messages.success(self.request, _('Your changes have been saved.'))
                return redirect(self.get_success_url())
        return self.get(request, *args, **kwargs)

    def get_success_url(self) -> str:
        return reverse('control:event.item.addons', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    def get_context_data(self, **kwargs) -> dict:
        self.object = self.get_object()
        context = super().get_context_data(**kwargs)
        context['formset'] = self.formset
        return context


class ItemDelete(EventPermissionRequiredMixin, DeleteView):
    model = Item
    template_name = 'pretixcontrol/item/delete.html'
    permission = 'can_change_items'
    context_object_name = 'item'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.is_allowed()
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
        if self.is_allowed():
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
