from django.forms import ModelForm

from pretix.base.models import WaitingListEntry


class WaitingListReorderForm(ModelForm):
    class Meta:
        model = WaitingListEntry
        fields = ['priority']
