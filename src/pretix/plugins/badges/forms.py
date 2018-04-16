from django import forms

from pretix.plugins.badges.models import BadgeLayout


class BadgeLayoutForm(forms.ModelForm):
    class Meta:
        model = BadgeLayout
        fields = ('name',)
