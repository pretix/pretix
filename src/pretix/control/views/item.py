from itertools import product
from django.contrib import messages
from django.db import transaction
from django.forms import BooleanField
from django.utils.functional import cached_property

from django.views.generic import ListView
from django.views.generic.edit import DeleteView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.core.urlresolvers import resolve, reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import redirect
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext_lazy as _
from pretix.base.forms import VersionedModelForm, I18nModelForm

from pretix.base.models import (
    Item, ItemCategory, Property, ItemVariation, PropertyValue, Question, Quota,
    Versionable)
from pretix.control.permissions import EventPermissionRequiredMixin, event_permission_required
from pretix.control.views.forms import TolerantFormsetModelForm, VariationsField, I18nInlineFormSet
from pretix.control.signals import restriction_formset
from . import UpdateView, CreateView


class ItemList(ListView):
    model = Item
    context_object_name = 'items'
    template_name = 'pretixcontrol/items/index.html'

    def get_queryset(self):
        return Item.objects.current.filter(
            event=self.request.event
        ).prefetch_related("category")


class CategoryForm(VersionedModelForm):

    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name'
        ]


class CategoryDelete(EventPermissionRequiredMixin, DeleteView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'pretixcontrol/items/category_delete.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_object(self, queryset=None) -> ItemCategory:
        return self.request.event.categories.current.get(
            identity=self.kwargs['category']
        )

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        for item in self.object.items.current.all():
            # TODO: Clone!?
            item.category = None
            item.save()
        success_url = self.get_success_url()
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
        return self.request.event.categories.current.get(
            identity=url.kwargs['category']
        )

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
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

    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new category has been created.'))
        return super().form_valid(form)


class CategoryList(ListView):
    model = ItemCategory
    context_object_name = 'categories'
    template_name = 'pretixcontrol/items/categories.html'

    def get_queryset(self):
        return self.request.event.categories.current.all()


def category_move(request, category, up=True):
    """
    This is a helper function to avoid duplicating code in category_move_up and
    category_move_down. It takes a category and a direction and then tries to bring
    all categories for this event in a new order.
    """
    category = request.event.categories.current.get(
        identity=category
    )
    categories = list(request.event.categories.current.order_by("position"))

    index = categories.index(category)
    if index != 0 and up:
        categories[index - 1], categories[index] = categories[index], categories[index - 1]
    elif index != len(categories) - 1 and not up:
        categories[index + 1], categories[index] = categories[index], categories[index + 1]

    for i, cat in enumerate(categories):
        if cat.position != i:
            cat.position = i
            cat.save()  # TODO: Clone or document sloppiness?


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


class PropertyList(ListView):
    model = Property
    context_object_name = 'properties'
    template_name = 'pretixcontrol/items/properties.html'

    def get_queryset(self):
        return Property.objects.current.filter(
            event=self.request.event
        )


class PropertyForm(VersionedModelForm):
    class Meta:
        model = Property
        localized_fields = '__all__'
        fields = [
            'name',
        ]


class PropertyValueForm(TolerantFormsetModelForm):
    class Meta:
        model = PropertyValue
        localized_fields = '__all__'
        fields = [
            'value',
        ]


class PropertyUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'pretixcontrol/items/property.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_object(self, queryset=None) -> Property:
        return self.request.event.properties.current.get(
            identity=self.kwargs['property']
        )

    def get_success_url(self) -> str:
        return reverse('control:event.items.properties.edit', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'property': self.kwargs['property']
        })

    def get_formset(self):
        formsetclass = inlineformset_factory(
            Property, PropertyValue,
            form=PropertyValueForm,
            formset=I18nInlineFormSet,
            can_order=True,
            extra=0,
        )
        kwargs = self.get_form_kwargs()
        kwargs['queryset'] = self.object.values.current.all()
        formset = formsetclass(**kwargs)
        return formset

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['formset'] = self.get_formset()
        return context

    @transaction.atomic()
    def form_valid(self, form, formset):
        for f in formset.deleted_forms:
            f.instance.delete()
            f.instance.pk = None

        for i, f in enumerate(formset.ordered_forms):
            if f.instance.pk is not None:
                f.instance = f.instance.clone()
            f.instance.position = i
            f.instance.save()

        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        formset = self.get_formset()
        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form)


class PropertyCreate(EventPermissionRequiredMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'pretixcontrol/items/property.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_success_url(self) -> str:
        return reverse('control:event.items.properties', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_formset(self):
        formsetclass = inlineformset_factory(
            Property, PropertyValue,
            form=PropertyValueForm,
            formset=I18nInlineFormSet,
            can_order=True,
            extra=3,
        )
        formset = formsetclass(**self.get_form_kwargs())
        return formset

    def get_context_data(self, *args, **kwargs) -> dict:
        self.object = None
        context = super().get_context_data(*args, **kwargs)
        context['formset'] = self.get_formset()
        return context

    @transaction.atomic()
    def form_valid(self, form, formset):
        form.instance.event = self.request.event
        resp = super().form_valid(form)
        for i, f in enumerate(formset.ordered_forms):
            f.instance.position = i
            f.instance.prop = form.instance
            f.instance.save()
        messages.success(self.request, _('The new property has been created.'))
        return resp

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        formset = self.get_formset()
        if form.is_valid() and formset.is_valid():
            return self.form_valid(form, formset)
        else:
            return self.form_invalid(form)


class PropertyDelete(EventPermissionRequiredMixin, DeleteView):
    model = Property
    form_class = PropertyForm
    template_name = 'pretixcontrol/items/property_delete.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = self.get_object().items.current.all()
        context['possible'] = self.is_allowed()
        return context

    def is_allowed(self) -> bool:
        return self.get_object().items.current.count() == 0

    def get_object(self, queryset=None) -> Property:
        if not hasattr(self, 'object') or not self.object:
            self.object = self.request.event.properties.current.get(
                identity=self.kwargs['property']
            )
        return self.object

    def delete(self, request, *args, **kwargs):
        if self.is_allowed():
            success_url = self.get_success_url()
            self.get_object().delete()
            messages.success(request, _('The selected property has been deleted.'))
            return HttpResponseRedirect(success_url)
        else:
            return HttpResponseForbidden()

    def get_success_url(self) -> str:
        return reverse('control:event.items.properties', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class QuestionList(ListView):
    model = Question
    context_object_name = 'questions'
    template_name = 'pretixcontrol/items/questions.html'

    def get_queryset(self):
        return self.request.event.questions.current.all()


class QuestionForm(VersionedModelForm):

    class Meta:
        model = Question
        localized_fields = '__all__'
        fields = [
            'question',
            'type',
            'required',
        ]


class QuestionDelete(EventPermissionRequiredMixin, DeleteView):
    model = Question
    template_name = 'pretixcontrol/items/question_delete.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None) -> Question:
        return self.request.event.questions.current.get(
            identity=self.kwargs['question']
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = list(self.get_object().items.current.all())
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
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
        return self.request.event.questions.current.get(
            identity=self.kwargs['question']
        )

    def form_valid(self, form):
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

    def get_success_url(self) -> str:
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new question has been created.'))
        return super().form_valid(form)


class QuotaList(ListView):
    model = Quota
    context_object_name = 'quotas'
    template_name = 'pretixcontrol/items/quotas.html'

    def get_queryset(self):
        return Quota.objects.current.filter(
            event=self.request.event
        ).prefetch_related("items")


class QuotaForm(I18nModelForm):

    def __init__(self, **kwargs):
        items = kwargs['items']
        del kwargs['items']
        super().__init__(**kwargs)

        if hasattr(self, 'instance'):
            active_items = set(self.instance.items.all())
            active_variations = set(self.instance.variations.all())
        else:
            active_items = set()
            active_variations = set()

        for item in items:
            if len(item.properties.all()) > 0:
                self.fields['item_%s' % item.identity] = VariationsField(
                    item, label=_("Activate for"),
                    required=False,
                    initial=active_variations
                )
                self.fields['item_%s' % item.identity].set_item(item)
            else:
                self.fields['item_%s' % item.identity] = BooleanField(
                    label=_("Activate"),
                    required=False,
                    initial=(item in active_items)
                )

    def save(self, commit=True):
        if self.instance.pk is not None and isinstance(self.instance, Versionable):
            if self.has_changed():
                self.instance = self.instance.clone_shallow()
        return super().save(commit)

    class Meta:
        model = Quota
        localized_fields = '__all__'
        fields = [
            'name',
            'size',
        ]


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
            item.field = self.get_form(QuotaForm)['item_%s' % item.identity]
        return context

    @transaction.atomic()
    def form_valid(self, form):
        res = super().form_valid(form)
        # The following commented-out checks are not necessary as both self.object.items
        # and self.object.variations can be expected empty due to the performance
        # optimization of pretixbase.models.Versionable.clone_shallow()
        # items = self.object.items.all()
        # variations = self.object.variations.all()
        selected_variations = []
        self.object = form.instance
        for item in self.items:
            field = form.fields['item_%s' % item.identity]
            data = form.cleaned_data['item_%s' % item.identity]
            if isinstance(field, VariationsField):
                for v in data:
                    selected_variations.append(v)
            if data:  # and item not in items:
                self.object.items.add(item)
            # elif not data and item in items:
            #     self.object.items.remove(item)

        self.object.variations.add(*[v for v in selected_variations])  # if v not in variations])
        # self.object.variations.remove(*[v for v in variations if v not in selected_variations])
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

    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new quota has been created.'))
        return super().form_valid(form)


class QuotaUpdate(EventPermissionRequiredMixin, QuotaEditorMixin, UpdateView):
    model = Quota
    form_class = QuotaForm
    template_name = 'pretixcontrol/items/quota.html'
    permission = 'can_change_items'
    context_object_name = 'quota'

    def get_object(self, queryset=None) -> Quota:
        return self.request.event.quotas.current.get(
            identity=self.kwargs['quota']
        )

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
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
        return self.request.event.quotas.current.get(
            identity=self.kwargs['quota']
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = list(self.get_object().items.current.all())
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
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
        if not hasattr(self, 'object') or not self.object:
            self.item = self.request.event.items.current.get(
                identity=self.kwargs['item']
            )
            self.object = self.item
        return self.object


class ItemFormGeneral(VersionedModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.current.all()
        self.fields['properties'].queryset = self.instance.event.properties.current.all()
        self.fields['questions'].queryset = self.instance.event.questions.current.all()

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'active',
            'admission',
            'short_description',
            'long_description',
            'default_price',
            'tax_rate',
            'properties',
            'questions',
        ]


class ItemCreate(EventPermissionRequiredMixin, CreateView):
    form_class = ItemFormGeneral
    template_name = 'pretixcontrol/item/index.html'
    permission = 'can_change_items'

    def get_success_url(self) -> str:
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.object.identity,
        })

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

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
            'item': self.get_object().identity,
        })

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)


class ItemVariationForm(VersionedModelForm):

    class Meta:
        model = ItemVariation
        localized_fields = '__all__'
        fields = [
            'active',
            'default_price',
        ]


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
                prefix=",".join([str(i.identity) for i in values]),
            )
        else:
            inst = ItemVariation(item=self.object)
            inst.item_id = self.object.identity
            inst.creation = True
            form = ItemVariationForm(
                data,
                instance=inst,
                prefix=",".join([str(i.identity) for i in values]),
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
                    v.identity for v in sorted(values, key=lambda v: v.prop.identity)
                    if v.prop.identity != prop2.identity
                ]

            def sort(v):
                # Given a list of variations, this will sort them by their position
                # on the x-axis
                return v[prop2.identity].sortkey

            # We now iterate over the cartesian product of all the other
            # properties which are NOT on the axes of the grid because we
            # create one grid for any combination of them.
            for gridrow in product(*[prop.values.current.all() for prop in self.properties[2:]]):
                grids = []
                for val1 in prop1.values.current.all():
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

                forms.append({'row': ", ".join([value.value for value in gridrow]), 'forms': grids})

        return forms, forms_flat

    def main(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.properties = list(self.object.properties.current.all().prefetch_related("values"))
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
            'item': self.get_object().identity,
        })

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        context['forms'] = self.forms
        context['properties'] = self.properties
        return context


class ItemRestrictions(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):

    permission = 'can_change_items'
    template_name = 'pretixcontrol/item/restrictions.html'

    def get_formsets(self):
        responses = restriction_formset.send(self.object.event, item=self.object)
        formsets = []
        for receiver, response in responses:
            response['formset'] = response['formsetclass'](
                self.request.POST if self.request.method == 'POST' else None,
                instance=self.object,
                prefix=response['prefix'],
            )
            formsets.append(response)
        return formsets

    def main(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.request = request
        self.formsets = self.get_formsets()

    def get(self, request, *args, **kwargs):
        self.main(request, *args, **kwargs)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        self.main(request, *args, **kwargs)
        valid = True
        for f in self.formsets:
            valid &= f['formset'].is_valid()
        if valid:
            for f in self.formsets:
                for form in f['formset']:
                    if 'DELETE' in form.cleaned_data and form.cleaned_data['DELETE'] is True:
                        if form.instance.pk is None:
                            continue
                        form.instance.delete()
                    else:
                        form.instance.event = request.event
                        form.instance.item = self.object
                        form.save()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            context = self.get_context_data(object=self.object)
            return self.render_to_response(context)

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['formsets'] = self.formsets
        return context

    def get_success_url(self) -> str:
        return reverse('control:event.item.restrictions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.object.identity
        })
