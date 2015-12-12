from itertools import product

from django.contrib import messages
from django.core.urlresolvers import resolve, reverse
from django.db import transaction
from django.forms.models import inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import DeleteView

from pretix.base.models import (
    Item, ItemCategory, ItemVariation, Property, PropertyValue, Question,
    Quota,
)
from pretix.control.forms import (
    NestedInnerI18nInlineFormSet, VariationsField, nestedformset_factory,
)
from pretix.control.forms.item import (
    CategoryForm, ItemFormGeneral, ItemVariationForm, PropertyForm,
    PropertyValueForm, QuestionForm, QuotaForm,
)
from pretix.control.permissions import (
    EventPermissionRequiredMixin, event_permission_required,
)

from . import CreateView, UpdateView


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

    @transaction.atomic()
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

    @transaction.atomic()
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

    @transaction.atomic()
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new category has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.category.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret


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
    messages.success(request, _('The order of categories as been updated.'))


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

    @transaction.atomic()
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


class QuestionUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = 'pretixcontrol/items/question.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None) -> Question:
        try:
            return self.request.event.questions.get(
                id=self.kwargs['question']
            )
        except Question.DoesNotExist:
            raise Http404(_("The requested question does not exist."))

    @transaction.atomic()
    def form_valid(self, form):
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


class QuestionCreate(EventPermissionRequiredMixin, CreateView):
    model = Question
    form_class = QuestionForm
    template_name = 'pretixcontrol/items/question.html'
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

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _('The new question has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.question.added', user=self.request.user, data=dict(form.cleaned_data))
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
        return list(self.request.event.items.all().prefetch_related("properties", "variations"))

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

    @transaction.atomic()
    def form_valid(self, form):
        res = super().form_valid(form)
        items = self.object.items.all()
        variations = self.object.variations.all()
        selected_variations = []
        self.object = form.instance
        for item in self.items:
            field = form.fields['item_%s' % item.id]
            data = form.cleaned_data['item_%s' % item.id]
            if isinstance(field, VariationsField):
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
    template_name = 'pretixcontrol/items/quota.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_success_url(self) -> str:
        return reverse('control:event.items.quotas', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic()
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new quota has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.quota.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret


class QuotaUpdate(EventPermissionRequiredMixin, QuotaEditorMixin, UpdateView):
    model = Quota
    form_class = QuotaForm
    template_name = 'pretixcontrol/items/quota.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_object(self, queryset=None) -> Quota:
        try:
            return self.request.event.quotas.get(
                id=self.kwargs['quota']
            )
        except Quota.DoesNotExist:
            raise Http404(_("The requested quota does not exist."))

    @transaction.atomic()
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
        return reverse('control:event.items.quotas', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


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

    @transaction.atomic()
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
    form_class = ItemFormGeneral
    template_name = 'pretixcontrol/item/index.html'
    permission = 'can_change_items'

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.object.id,
        })

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.item.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        newinst = Item(event=self.request.event)
        kwargs = super().get_form_kwargs()
        kwargs.update({'instance': newinst})
        return kwargs


class ItemUpdateGeneral(ItemDetailMixin, EventPermissionRequiredMixin, UpdateView):
    form_class = ItemFormGeneral
    template_name = 'pretixcontrol/item/index.html'
    permission = 'can_change_items'

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.item.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)


class ItemProperties(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_items'
    template_name = 'pretixcontrol/item/properties.html'

    def get_success_url(self) -> str:
        return reverse('control:event.item.properties', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    def get_inner_formset_class(self):
        formsetclass = inlineformset_factory(
            Property, PropertyValue,
            form=PropertyValueForm,
            formset=NestedInnerI18nInlineFormSet,
            can_order=True, extra=0
        )
        return formsetclass

    def get_outer_formset(self):
        formsetclass = nestedformset_factory(
            Property, [self.get_inner_formset_class()],
            form=PropertyForm, can_order=False, can_delete=True, extra=0
        )
        formset = formsetclass(self.request.POST if self.request.method == "POST" else None,
                               queryset=Property.objects.filter(item=self.object).prefetch_related('values'),
                               event=self.request.event)
        return formset

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.get_outer_formset()
        return ctx

    @transaction.atomic()
    def form_valid(self, formset):
        for f in formset:
            f.instance.event = self.request.event
            f.instance.item = self.get_object()
            is_created = not f.instance.pk
            f.instance.save()
            if f.has_changed() and not is_created:
                change_data = {
                    k: f.cleaned_data.get(k) for k in f.changed_data
                }
                change_data['id'] = f.instance.pk
                f.instance.item.log_action(
                    'pretix.event.item.property.changed', user=self.request.user, data=change_data
                )
            elif is_created:
                change_data = dict(f.cleaned_data)
                change_data['id'] = f.instance.pk
                f.instance.item.log_action(
                    'pretix.event.item.property.added', user=self.request.user, data=change_data
                )

            for n in f.nested:

                for fn in n.deleted_forms:
                    f.instance.item.log_action(
                        'pretix.event.item.property.value.deleted', user=self.request.user, data={
                            'id': fn.instance.pk
                        }
                    )
                    fn.instance.delete()
                    fn.instance.pk = None

                for i, fn in enumerate(n.ordered_forms + [ef for ef in n.extra_forms if ef not in n.ordered_forms]):
                    fn.instance.position = i
                    fn.instance.prop = f.instance
                    fn.save()
                    if f.has_changed():
                        change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
                        change_data['id'] = f.instance.pk
                        f.instance.item.log_action(
                            'pretix.event.item.property.value.changed', user=self.request.user, data=change_data
                        )

                for form in n.extra_forms:
                    if not form.has_changed():
                        continue
                    if n.can_delete and n._should_delete_form(form):
                        continue
                    change_data = dict(f.cleaned_data)
                    n.save_new(form)
                    change_data['id'] = form.instance.pk
                    f.instance.item.log_action(
                        'pretix.event.item.property.value.added', user=self.request.user, data=change_data
                    )
        messages.success(self.request, _('Your changes have been saved.'))
        return redirect(self.get_success_url())

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        formset = self.get_outer_formset()
        if formset.is_valid():
            return self.form_valid(formset)
        else:
            return self.get(request, *args, **kwargs)


class ItemVariations(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_items'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = None

    def get_form(self, variation, data=None) -> ItemVariationForm:
        """
        Return the dict for one given variation. Variations are expected to be
        dictionaries in the format of Item.get_all_variations()
        """
        # Values are all dictionary ite
        values = [i[1] for i in sorted([it for it in variation.items() if it[0] != 'variation'])]
        if 'variation' in variation:
            form = ItemVariationForm(
                data,
                instance=variation['variation'],
                prefix=",".join([str(i.id) for i in values]),
            )
        else:
            inst = ItemVariation(item=self.object)
            inst.item_id = self.object.id
            inst.creation = True
            form = ItemVariationForm(
                data,
                instance=inst,
                prefix=",".join([str(i.id) for i in values]),
            )
        form.values = values
        return form

    def get_forms(self) -> tuple:
        """
        Returns one form per possible item variation. The forms are returned
        twice: The first entry in the returned tuple contains a 1-, 2- or
        3-dimensional list, depending on the number of properties associated
        with this item (this is being used for form display), the second
        contains all forms in one single list (this is used for processing).

        The first, hierarchical list, is a list of dicts on all levels but the
        last one, where the dict contains the two entries 'row' containing a
        string describing this layer and 'forms' which contains the forms or
        the next list of dicts.
        """
        forms = []
        forms_flat = []
        variations = self.object.get_all_variations()
        data = self.request.POST if self.request.method == 'POST' else None

        if self.dimension == 1:
            # For one-dimensional structures we just have a list of forms
            for variation in variations:
                form = self.get_form(variation, data)
                forms.append(form)
            forms_flat = forms

        elif self.dimension >= 2:
            # For 2 or more dimensional structures we display a list of grids
            # of forms

            # prop1 is the property on all the grid's y-axes
            prop1 = self.properties[0]
            # prop2 is the property on all the grid's x-axes
            prop2 = self.properties[1]

            def selector(values):
                # Given an iterable of PropertyValue objects, this will return a
                # list of their primary keys, ordered by the primary keys of the
                # properties they belong to EXCEPT the value for the property prop2.
                # We'll see later why we need this.
                return [
                    v.id for v in sorted(values, key=lambda v: v.prop.id)
                    if v.prop.id != prop2.id
                ]

            def sort(v):
                # Given a list of variations, this will sort them by their position
                # on the x-axis
                return v[prop2.id].sortkey

            # We now iterate over the cartesian product of all the other
            # properties which are NOT on the axes of the grid because we
            # create one grid for any combination of them.
            for gridrow in product(*[prop.values.all() for prop in self.properties[2:]]):
                grids = []
                for val1 in prop1.values.all():
                    formrow = []
                    # We are now inside one of the rows of the grid and have to
                    # select the variations to display in this row. In order to
                    # achieve this, we use the 'selector' lambda defined above.
                    # It gives us a normalized, comparable version of a set of
                    # PropertyValue objects. In this case, we compute the
                    # selector of our row as the selector of the sum of the
                    # values defining our grind and the value defining our row.
                    selection = selector(gridrow + (val1,))
                    # We now iterate over all variations who generate the same
                    # selector as 'selection'.
                    filtered = [v for v in variations if selector(v.relevant_values()) == selection]
                    for variation in sorted(filtered, key=sort):
                        form = self.get_form(variation, data)
                        formrow.append(form)
                        forms_flat.append(form)

                    grids.append({'row': val1, 'forms': formrow})

                forms.append({'row': ", ".join([str(value.value) for value in gridrow]), 'forms': grids})

        return forms, forms_flat

    def main(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.properties = list(self.object.properties.all().prefetch_related("values"))
        self.dimension = len(self.properties)
        self.forms, self.forms_flat = self.get_forms()

    def get(self, request, *args, **kwargs):
        self.main(request, *args, **kwargs)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.main(request, *args, **kwargs)
        context = self.get_context_data(object=self.object)
        valid = True
        with transaction.atomic():
            for form in self.forms_flat:
                if form.is_valid() and form.has_changed():
                    form.save()
                    change_data = {
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                    change_data['id'] = form.instance.pk
                    self.object.log_action(
                        'pretix.event.item.variation.changed', user=self.request.user, data=change_data
                    )
                    if hasattr(form.instance, 'creation') and form.instance.creation:
                        # We need this special 'creation' field set to true in get_form
                        # for newly created items as cleanerversion does already set the
                        # primary key in its post_init hook
                        form.instance.values.add(*form.values)
                elif not form.is_valid and form.has_changed():
                    valid = False
        if valid:
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        return self.render_to_response(context)

    def get_template_names(self) -> "List[str]":
        if self.dimension == 0:
            return ['pretixcontrol/item/variations_0d.html']
        elif self.dimension == 1:
            return ['pretixcontrol/item/variations_1d.html']
        elif self.dimension >= 2:
            return ['pretixcontrol/item/variations_nd.html']

    def get_success_url(self) -> str:
        return reverse('control:event.item.variations', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().id,
        })

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context['forms'] = self.forms
        context['properties'] = self.properties
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
        return not self.get_object().positions.exists()

    def get_object(self, queryset=None) -> Property:
        if not hasattr(self, 'object') or not self.object:
            try:
                self.object = self.request.event.items.get(
                    id=self.kwargs['item']
                )
            except Property.DoesNotExist:
                raise Http404(_("The requested product does not exist."))
        return self.object

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        if self.is_allowed():
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
