from pretix.base.forms import I18nModelForm
from pretix.base.models import WaitingListEntry
from django_scopes import scopes_disabled

with scopes_disabled():
    class WaitingListEntryEditForm(I18nModelForm):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['subevent'].required = True
            self.fields['subevent'].empty_label = None
            self.fields['subevent'].queryset = self.event.subevents.all()

        class Meta:
            model = WaitingListEntry
            localized_fields = '__all__'
            fields = [
                'subevent',
            ]
