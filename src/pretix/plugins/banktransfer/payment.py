from collections import OrderedDict
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
             label=_('Bank account details')
         ))
    ])
