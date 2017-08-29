from django import forms

from pretix.plugins.pretixdroid.models import AppConfiguration


class AppConfigurationForm(forms.ModelForm):
    class Meta:
        model = AppConfiguration
        fields = ('all_items', 'items', 'subevent', 'show_info', 'allow_search')
        widgets = {
            'items': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '#id_all_items'
            }),
        }

    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(**kwargs)
        self.fields['items'].queryset = self.event.items.all()
        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
        else:
            del self.fields['subevent']
