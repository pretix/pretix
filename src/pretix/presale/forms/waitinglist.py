from django import forms

from pretix.base.models import WaitingListEntry


class WaitingListForm(forms.ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
