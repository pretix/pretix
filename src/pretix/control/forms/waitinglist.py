from django.urls import reverse
from django_scopes.forms import SafeModelChoiceField

from pretix.base.forms import I18nModelForm
from pretix.base.models import WaitingListEntry
from pretix.control.forms.widgets import Select2


class WaitingListEntryTransferForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].required = True
            self.fields['subevent'].queryset = self.event.subevents.filter(active=True)
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices

    class Meta:
        model = WaitingListEntry
        fields = [
            'subevent',
        ]
        field_classes = {
            'subevent': SafeModelChoiceField,
        }
