from pretix.base.forms import I18nModelForm
from pretix.base.models import WaitingListEntry
from django_scopes import scopes_disabled
from django.forms.utils import ErrorDict

with scopes_disabled():
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

        #def full_clean(self):
        #    if len(self.data) == 0:
        #        # form wasn't submitted
        #        self._errors = ErrorDict()
        #        return
        #    super().full_clean()

'''
        def save(self, commit=True):
            objs = list(self.queryset)
            print("hi1")
            fields = set()

            for k in self.fields:
                print("hi1.5")
                fields.add(k)
                for obj in objs:
                    setattr(obj, k, self.cleaned_data[k])

            if fields:
                WaitingListEntry.objects.bulk_update(objs, fields, 200)
                print("hi2")
'''