from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.plugins.badges.models import BadgeItem, BadgeLayout


class BadgeLayoutForm(forms.ModelForm):
    class Meta:
        model = BadgeLayout
        fields = ('name',)


class BadgeItemForm(forms.ModelForm):
    class Meta:
        model = BadgeItem
        fields = ('layout',)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['layout'].label = _('Badge layout')
        self.fields['layout'].empty_label = _('(Event default)')
        self.fields['layout'].queryset = event.badge_layouts.all()
        self.fields['layout'].required = False

    def save(self, commit=True):
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)
