from collections import OrderedDict
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from django import forms

from pretix.base.payment import BasePaymentProvider


class BankTransfer(BasePaymentProvider):
    identifier = 'banktransfer'
    verbose_name = _('Bank transfer')
    settings_form_fields = OrderedDict([
        ('bank_details',
         forms.CharField(
             widget=forms.Textarea,
             label=_('Bank account details'),
             required=False
         ))
    ])

    def checkout_form_render(self, request) -> str:
        template = get_template('pretixplugins/banktransfer/checkout_payment_form.html')
        ctx = Context({'request': request, 'event': self.event, 'settings': self.settings})
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        return True
