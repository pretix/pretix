from pretix.base.forms import I18nModelForm
from pretix.base.models import WaitingListEntry
from django_scopes import scopes_disabled
from django.forms.utils import ErrorDict

class WaitingListEntryEditForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        self.queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        self.fields['subevent'].required = True
        self.fields['subevent'].empty_label = None
        self.fields['subevent'].queryset = self.event.subevents.filter(active=True)

    class Meta:
        model = WaitingListEntry
        fields = [
            'subevent',
        ]
