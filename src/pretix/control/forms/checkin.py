from django import forms

from pretix.base.models.checkin import CheckinList


class CheckinListForm(forms.ModelForm):
    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.pop('locales', None)
        super().__init__(**kwargs)
        self.fields['limit_products'].queryset = self.event.items.all()
        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].required = True
        else:
            del self.fields['subevent']

    class Meta:
        model = CheckinList
        localized_fields = '__all__'
        fields = [
            'name',
            'all_products',
            'limit_products',
            'subevent'
        ]
        widgets = {
            'limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]'
            }),
        }
