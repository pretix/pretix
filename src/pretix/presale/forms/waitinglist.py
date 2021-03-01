from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.forms.questions import NamePartsFormField
from pretix.base.models import WaitingListEntry


class WaitingListForm(forms.ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = ('name_parts', 'email', 'phone')

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        self.fields['name_parts'] = NamePartsFormField(
            max_length=255,
            required=False,
            scheme=self.event.settings.name_scheme,
            titles=self.event.settings.name_scheme_titles,
            label=_('Name'),
        )
