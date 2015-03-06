from collections import OrderedDict
from django.utils.translation import ugettext_lazy as _
from django import forms

from pretix.base.payment import BasePaymentProvider


class Stripe(BasePaymentProvider):
    identifier = 'stripe'
    verbose_name = _('Credit Card via Stripe')
    settings_form_fields = OrderedDict([
    ])
    checkout_form_fields = OrderedDict([
        ('cc_number',
         forms.CharField(
             label=_('Credit card number'),
             required=False
         ))
    ])
