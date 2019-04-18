from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.services import tickets

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
        self.event = kwargs.pop('event')
        self.sales_channel = kwargs.pop('sales_channel')
        super().__init__(*args, **kwargs)
        if self.sales_channel.identifier != 'web':
            self.fields['layout'].label = _('PDF ticket layout for {channel}').format(
                channel=self.sales_channel.verbose_name
            )
            self.fields['layout'].empty_label = _('(Same as above)')
        else:
            self.fields['layout'].label = _('PDF ticket layout')
            self.fields['layout'].empty_label = _('(Event default)')
        self.fields['layout'].queryset = self.event.ticket_layouts.all()
        self.fields['layout'].required = False

    def save(self, commit=True):
        self.instance.sales_channel = self.sales_channel.identifier
        if self.cleaned_data['layout'] is None:
            if self.instance.pk:
                self.instance.delete()
            else:
                return
        else:
            return super().save(commit=commit)
        tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk, 'provider': 'pdf',
                                                     'item': self.instance.item_id})
