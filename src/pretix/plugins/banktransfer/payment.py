from pretix.base.payment import BasePaymentProvider
from django.utils.translation import ugettext_lazy as _


class BankTransfer(BasePaymentProvider):
    identifier = 'banktransfer'
    verbose_name = _('Bank transfer')
    settings_form_fields = {

    }
