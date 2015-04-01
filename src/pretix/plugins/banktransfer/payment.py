from collections import OrderedDict
import json
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from django import forms

from pretix.base.payment import BasePaymentProvider


class BankTransfer(BasePaymentProvider):
    identifier = 'banktransfer'
    verbose_name = _('Bank transfer')

    @property
    def settings_form_fields(self):
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('bank_details',
                 forms.CharField(
                     widget=forms.Textarea,
                     label=_('Bank account details'),
                     required=False
                 ))
            ]
        )

    def checkout_form_render(self, request) -> str:
        template = get_template('pretixplugins/banktransfer/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        return True

    def checkout_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request):
        form = self.checkout_form(request)
        template = get_template('pretixplugins/banktransfer/checkout_payment_confirm.html')
        ctx = {'request': request, 'form': form, 'settings': self.settings}
        return template.render(ctx)

    def order_pending_render(self, request, order) -> str:
        template = get_template('pretixplugins/banktransfer/pending.html')
        ctx = {'request': request, 'order': order, 'settings': self.settings}
        return template.render(ctx)

    def order_control_render(self, request, order) -> str:
        if order.payment_info:
            payment_info = json.loads(order.payment_info)
            payment_info['amount'] /= 100
        else:
            payment_info = None
        template = get_template('pretixplugins/banktransfer/control.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings,
               'payment_info': payment_info, 'order': order}
        return template.render(ctx)
