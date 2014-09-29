from itertools import product

from django.views.generic import ListView
from django.views.generic.edit import UpdateView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.core.urlresolvers import resolve, reverse
from django import forms

from tixlbase.models import Item, ItemCategory, Property, ItemVariation
from tixlcontrol.permissions import EventPermissionRequiredMixin


class ItemList(ListView):
    model = Item
    context_object_name = 'items'
    template_name = 'tixlcontrol/items/index.html'

    def get_queryset(self):
        return Item.objects.filter(
            event=self.request.event
        )


class CategoryList(ListView):
    model = ItemCategory
    context_object_name = 'items'
    template_name = 'tixlcontrol/items/index.html'

    def get_queryset(self):
        return ItemCategory.objects.filter(
            event=self.request.event
        )


class PropertyList(ListView):
    model = Property
    context_object_name = 'items'
    template_name = 'tixlcontrol/items/index.html'

    def get_queryset(self):
        return Property.objects.filter(
            event=self.request.event
        )


class ItemUpdateFormGeneral(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.instance.event.categories.all()
        self.fields['properties'].queryset = self.instance.event.properties.all()

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
        ]


class ItemUpdateGeneral(EventPermissionRequiredMixin, UpdateView):
    model = Item
    form_class = ItemUpdateFormGeneral
    template_name = 'tixlcontrol/item/index.html'
    permission = 'can_change_items'
    context_object_name = 'item'

    def get_object(self, queryset=None):
        url = resolve(self.request.path_info)
        return self.request.event.items.get(
            id=url.kwargs['item']
        )

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


class ItemVariations(TemplateView, SingleObjectMixin):

    model = Item
    context_object_name = 'item'

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

            for val1 in prop1.values.all().order_by("id"):
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

            # Given an dictionary like the ones returned by
            # Item.get_all_variation() this will return a list of PropertyValue
            # objects sorted by the primary keys of the properties they belong
            # to.
            values = lambda variation: [
                i[1] for i in sorted(
                    [it for it in variation.items() if it[0] != 'variation']
                )
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
                    filtered = [v for v in variations if selector(values(v)) == selection]
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

    def get_object(self, queryset=None):
        if not self.item:
            url = resolve(self.request.path_info)
            self.item = self.request.event.items.get(
                id=url.kwargs['item']
            )
        return self.item

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
