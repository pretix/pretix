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

    def get_forms(self):
        """
        Returns one form per possible item variation. The forms are returned
        twice: The first entry in the returned tuple contains a 1-, 2- or
        3-dimensional list, depending on the number of properties associated
        with this item (this is being used for form display), the second
        contains all forms in one single list (this is used for processing).
        """
        forms = []
        forms_flat = []
        variations = self.object.get_all_variations()
        data = self.request.POST if self.request.method == 'POST' else None
        if self.dimension == 1:
            for var in variations:
                val = [i[1] for i in sorted([it for it in var.items() if it[0] != 'variation'])]
                if 'variation' in var:
                    form = ItemVariationForm(
                        data,
                        instance=var['variation'],
                        prefix=",".join([str(i) for i in val])
                    )
                else:
                    form = ItemVariationForm(
                        data,
                        instance=ItemVariation(item=self.object),
                        prefix=",".join([str(i) for i in val])
                    )
                form.values = val
                forms.append(form)
            forms_flat = forms
        return forms, forms_flat

    def main(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.properties = self.object.properties.all()
        self.dimension = self.properties.count()
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['forms'] = self.forms
        context['properties'] = self.properties
        return context
