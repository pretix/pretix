from itertools import product

from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.core.urlresolvers import resolve, reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django import forms
from django.shortcuts import redirect
from django.forms.models import inlineformset_factory

from tixlbase.models import Item, ItemCategory, Property, ItemVariation, PropertyValue, Question
from tixlcontrol.permissions import EventPermissionRequiredMixin, event_permission_required
from tixlcontrol.views.forms import TolerantFormsetModelForm
from tixlcontrol.signals import restriction_formset


class ItemList(ListView):
    model = Item
    context_object_name = 'items'
    template_name = 'tixlcontrol/items/index.html'

    def get_queryset(self):
        return Item.objects.filter(
            event=self.request.event
        ).prefetch_related("category")


class CategoryForm(forms.ModelForm):

    class Meta:
        model = ItemCategory
        localized_fields = '__all__'
        fields = [
            'name'
        ]


class CategoryDelete(EventPermissionRequiredMixin, DeleteView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'tixlcontrol/items/category_delete.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.categories.get(
            id=url.kwargs['category']
        )

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.items.update(category=None)
        success_url = self.get_success_url()
        self.object.delete()
        return HttpResponseRedirect(success_url)

    def get_success_url(self):
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?deleted=true'


class CategoryUpdate(EventPermissionRequiredMixin, UpdateView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'tixlcontrol/items/category.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.categories.get(
            id=url.kwargs['category']
        )

    def get_success_url(self):
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?updated=true'


class CategoryCreate(EventPermissionRequiredMixin, CreateView):
    model = ItemCategory
    form_class = CategoryForm
    template_name = 'tixlcontrol/items/category.html'
    permission = 'can_change_items'
    context_object_name = 'category'

    def get_success_url(self):
        return reverse('control:event.items.categories', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?created=true'

    def form_valid(self, form):
        form.instance.event = self.request.event
        return super().form_valid(form)


class CategoryList(ListView):
    model = ItemCategory
    context_object_name = 'categories'
    template_name = 'tixlcontrol/items/categories.html'

    def get_queryset(self):
        return self.request.event.categories.all()


def category_move(request, organizer, event, category, up=True):
    category = request.event.categories.get(
        id=category
    )
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


@event_permission_required("can_change_items")
def category_move_up(request, organizer, event, category):
    category_move(request, organizer, event, category, up=True)
    return redirect(reverse('control:event.items.categories', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
    }) + '?ordered=true')


@event_permission_required("can_change_items")
def category_move_down(request, organizer, event, category):
    category_move(request, organizer, event, category, up=False)
    return redirect(reverse('control:event.items.categories', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
    }) + '?ordered=true')


class PropertyList(ListView):
    model = Property
    context_object_name = 'properties'
    template_name = 'tixlcontrol/items/properties.html'

    def get_queryset(self):
        return Property.objects.filter(
            event=self.request.event
        )


class PropertyForm(forms.ModelForm):
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
    template_name = 'tixlcontrol/items/property.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.properties.get(
            id=url.kwargs['property']
        )

    def get_success_url(self):
        url = resolve(self.request.path_info)
        return reverse('control:event.items.properties.edit', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'property': url.kwargs['property']
        }) + '?success=true'

    def get_formset(self):
        formsetclass = inlineformset_factory(
            Property, PropertyValue,
            form=PropertyValueForm,
            can_order=True,
            extra=0,
        )
        formset = formsetclass(**self.get_form_kwargs())
        return formset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['formset'] = self.get_formset()
        return context

    def form_valid(self, form, formset):
        for i, f in enumerate(formset.ordered_forms):
            f.instance.position = i
        formset.save()
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
    template_name = 'tixlcontrol/items/property.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_success_url(self):
        return reverse('control:event.items.properties', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?created=true'

    def get_formset(self):
        formsetclass = inlineformset_factory(
            Property, PropertyValue,
            form=PropertyValueForm,
            can_order=True,
            extra=3,
        )
        formset = formsetclass(**self.get_form_kwargs())
        return formset

    def get_context_data(self, *args, **kwargs):
        self.object = None
        context = super().get_context_data(*args, **kwargs)
        context['formset'] = self.get_formset()
        return context

    def form_valid(self, form, formset):
        form.instance.event = self.request.event
        resp = super().form_valid(form)
        for i, f in enumerate(formset.ordered_forms):
            f.instance.position = i
            f.instance.prop = form.instance
            f.instance.save()
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
    template_name = 'tixlcontrol/items/property_delete.html'
    permission = 'can_change_items'
    context_object_name = 'property'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = self.get_object().items.all()
        context['possible'] = self.is_allowed()
        return context

    def is_allowed(self):
        return self.get_object().items.count() == 0

    def get_object(self, queryset=None):
        if not hasattr(self, 'object') or not self.object:
            url = resolve(self.request.path_info)
            self.object = self.request.event.properties.get(
                id=url.kwargs['property']
            )
        return self.object

    def delete(self, request, *args, **kwargs):
        if self.is_allowed():
            success_url = self.get_success_url()
            self.get_object().delete()
            return HttpResponseRedirect(success_url)
        else:
            return HttpResponseForbidden()

    def get_success_url(self):
        return reverse('control:event.items.properties', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?deleted=true'


class QuestionList(ListView):
    model = Question
    context_object_name = 'questions'
    template_name = 'tixlcontrol/items/questions.html'

    def get_queryset(self):
        return self.request.event.questions.all()


class QuestionForm(forms.ModelForm):

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
    template_name = 'tixlcontrol/items/question_delete.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.questions.get(
            id=url.kwargs['question']
        )

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['dependent'] = list(self.get_object().items.all())
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.items.update(category=None)
        success_url = self.get_success_url()
        self.object.delete()
        return HttpResponseRedirect(success_url)

    def get_success_url(self):
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?deleted=true'


class QuestionUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = 'tixlcontrol/items/question.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.questions.get(
            id=url.kwargs['question']
        )

    def get_success_url(self):
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?updated=true'


class QuestionCreate(EventPermissionRequiredMixin, CreateView):
    model = Question
    form_class = QuestionForm
    template_name = 'tixlcontrol/items/question.html'
    permission = 'can_change_items'
    context_object_name = 'question'

    def get_success_url(self):
        return reverse('control:event.items.questions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + '?created=true'

    def form_valid(self, form):
        form.instance.event = self.request.event
        return super().form_valid(form)


class ItemDetailMixin(SingleObjectMixin):
    model = Item
    context_object_name = 'item'

    def get_object(self, queryset=None):
        if not hasattr(self, 'object') or not self.object:
            url = resolve(self.request.path_info)
            self.item = self.request.event.items.get(
                id=url.kwargs['item']
            )
            self.object = self.item
        return self.object


class ItemUpdateFormGeneral(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['properties'].queryset = self.instance.event.properties.all()
        self.fields['questions'].queryset = self.instance.event.questions.all()

    class Meta:
        model = Item
        localized_fields = '__all__'
        fields = [
            'category',
            'name',
            'active',
            'short_description',
            'long_description',
            'default_price',
            'tax_rate',
            'properties',
            'questions',
        ]


class ItemUpdateGeneral(ItemDetailMixin, EventPermissionRequiredMixin, UpdateView):
    form_class = ItemUpdateFormGeneral
    template_name = 'tixlcontrol/item/index.html'
    permission = 'can_change_items'

    def get_success_url(self):
        return reverse('control:event.item', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.get_object().pk,
        }) + '?success=true'


class ItemVariationForm(forms.ModelForm):

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

    def get_form(self, variation, data=None):
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
                prefix=",".join([str(i.pk) for i in values]),
            )
        else:
            form = ItemVariationForm(
                data,
                instance=ItemVariation(item=self.object),
                prefix=",".join([str(i.pk) for i in values]),
            )
        form.values = values
        return form

    def get_forms(self):
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

        elif self.dimension == 2:
            # For two-dimensional structures we have a grid of forms
            # prop1 is the property on the grid's y-axis
            prop1 = self.properties[0]
            # prop2 is the property on the grid's x-axis
            prop2 = self.properties[1]

            # Given a list of variations, this will sort them by their position
            # on the x-axis
            sort = lambda v: v[prop2.pk].pk

            for val1 in prop1.values.all():
                formrow = []
                # We are now inside a grid row. We iterate over all variations
                # which belong in this row and create forms for them. In order
                # to achieve this, we select all variation dictionaries which
                # have the same value for prop1 as our row does and sort them
                # by their value for prop2.
                filtered = [v for v in variations if v[prop1.pk].pk == val1.pk]
                for variation in sorted(filtered, key=sort):
                    form = self.get_form(variation, data)
                    formrow.append(form)
                    forms_flat.append(form)

                forms.append({'row': val1.value, 'forms': formrow})

        elif self.dimension > 2:
            # For 3 or more dimensional structures we display a list of grids
            # of forms

            # prop1 is the property on all the grid's y-axes
            prop1 = self.properties[0]
            # prop2 is the property on all the grid's x-axes
            prop2 = self.properties[1]

            # Given an iterable of PropertyValue objects, this will return a
            # list of their primary keys, ordered by the primary keys of the
            # properties they belong to EXCEPT the value for the property prop2.
            # We'll see later why we need this.
            selector = lambda values: [
                v.pk for v in sorted(values, key=lambda v: v.prop.pk)
                if v.prop.pk != prop2.pk
            ]

            # Given a list of variations, this will sort them by their position
            # on the x-axis
            sort = lambda v: v[prop2.pk].pk

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

                forms.append({'row': ", ".join([value.value for value in gridrow]), 'forms': grids})

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
        for form in self.forms_flat:
            if form.is_valid():
                if form.instance.pk is None:
                    form.save()
                    form.instance.values.add(*form.values)
                else:
                    form.save()
        return self.render_to_response(context)

    def get_template_names(self):
        if self.dimension == 1:
            return ['tixlcontrol/item/variations_1d.html']
        elif self.dimension == 2:
            return ['tixlcontrol/item/variations_2d.html']
        elif self.dimension > 2:
            return ['tixlcontrol/item/variations_nd.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['forms'] = self.forms
        context['properties'] = self.properties
        return context


class ItemRestrictions(ItemDetailMixin, EventPermissionRequiredMixin, TemplateView):

    permission = 'can_change_items'
    template_name = 'tixlcontrol/item/restrictions.html'

    def get_formsets(self):
        responses = restriction_formset.send(self.object.event, item=self.object)
        formsets = []
        for receiver, response in responses:
            response['formset'] = response['formsetclass'](
                self.request.POST if self.request.method == 'POST' else None,
                queryset=response['queryset'],
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
                        form.instance.save()
            return redirect(self.get_success_url())
        else:
            context = self.get_context_data(object=self.object)
            return self.render_to_response(context)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['formsets'] = self.formsets
        return context

    def get_success_url(self):
        return reverse('control:event.item.restrictions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'item': self.object.pk
        }) + '?success=true'
