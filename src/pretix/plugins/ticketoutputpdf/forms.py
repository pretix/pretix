from django import forms
from django.utils.translation import ugettext_lazy as _

from .models import TicketLayout, TicketLayoutItem


class TicketLayoutForm(forms.ModelForm):
    class Meta:
        model = TicketLayout
        fields = ('name',)


class TicketLayoutItemForm(forms.ModelForm):
    class Meta:
        model = TicketLayoutItem
        fields = ('layout',)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['layout'].label = _('PDF ticket layout')
        self.fields['layout'].queryset = event.ticket_layouts.all()
        self.fields['layout'].required = False

    def save(self, commit=True):
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)
