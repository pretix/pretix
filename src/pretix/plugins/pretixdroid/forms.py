from django import forms

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
