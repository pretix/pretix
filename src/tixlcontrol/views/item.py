from django.views.generic import ListView
from django.views.generic.edit import UpdateView
from django.core.urlresolvers import resolve, reverse
from django import forms

from tixlbase.models import Item, ItemCategory, Property
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
