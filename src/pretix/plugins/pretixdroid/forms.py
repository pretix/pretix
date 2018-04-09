from django import forms
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from pretix.control.forms.widgets import Select2
from pretix.plugins.pretixdroid.models import AppConfiguration


class AppConfigurationForm(forms.ModelForm):
    class Meta:
        model = AppConfiguration
        fields = ('all_items', 'items', 'list', 'show_info', 'allow_search', 'app')
        widgets = {
            'items': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_items'
            }),
            'app': forms.RadioSelect
        }

    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(**kwargs)
        self.fields['items'].queryset = self.event.items.all()
        self.fields['list'].queryset = self.event.checkin_lists.all()
        self.fields['list'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('Check-in list')
            }
        )
        self.fields['list'].widget.choices = self.fields['list'].choices
        self.fields['list'].required = True
