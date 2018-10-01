import json
import textwrap
from collections import OrderedDict

from django import forms
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nFormField, I18nTextarea
from i18nfield.strings import LazyI18nString

from pretix.base.models import OrderPayment
from pretix.base.payment import BasePaymentProvider


class BankTransfer(BasePaymentProvider):
    identifier = 'banktransfer'
    verbose_name = _('Bank transfer')
    abort_pending_allowed = True

    @staticmethod
    def form_field(**kwargs):
        return I18nFormField(
            label=_('Bank account details'),
            widget=I18nTextarea,
            help_text=_('Include everything that your customers need to send you a bank transfer payment. Within SEPA '
                        'countries, IBAN, BIC and account owner should suffice. If you have lots of international '
                        'customers, they might also need your full address and your bank\'s full address.'),
            widget_kwargs={'attrs': {
                'rows': '4',
                'placeholder': _(
                    'e.g. IBAN: DE12 1234 5678 8765 4321\n'
                    'BIC: GENEXAMPLE1\n'
                    'Account owner: John Doe\n'
                    'Name of Bank: Professional Banking Institute Ltd., London'
                )
            }},
            **kwargs
        )

    @property
    def settings_form_fields(self):
        d = OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('bank_details', self.form_field()),
                ('omit_hyphen', forms.BooleanField(
                    label=_('Do not include a hypen in the payment reference.'),
                    help_text=_('This is required in some countries.'),
                    required=False
                )),

            ]
        )
        d.move_to_end('bank_details', last=False)
        d.move_to_end('_enabled', last=False)
        return d

    def payment_form_render(self, request) -> str:
        template = get_template('pretixplugins/banktransfer/checkout_payment_form.html')
        ctx = {
            'request': request,
            'event': self.event,
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def checkout_prepare(self, request, total):
        return True

    def payment_prepare(self, request: HttpRequest, payment: OrderPayment):
        return True

    def payment_is_valid_session(self, request):
        return True

    def checkout_confirm_render(self, request):
        return self.payment_form_render(request)

    def order_pending_mail_render(self, order) -> str:
        template = get_template('pretixplugins/banktransfer/email/order_pending.txt')
        ctx = {
            'event': self.event,
            'order': order,
            'code': self._code(order),
            'details': textwrap.indent(str(self.settings.get('bank_details', as_type=LazyI18nString)), '    '),
        }
        return template.render(ctx)

    def payment_pending_render(self, request: HttpRequest, payment: OrderPayment):
        template = get_template('pretixplugins/banktransfer/pending.html')
        ctx = {
            'event': self.event,
            'code': self._code(payment.order),
            'order': payment.order,
            'details': self.settings.get('bank_details', as_type=LazyI18nString),
        }
        return template.render(ctx)

    def payment_control_render(self, request: HttpRequest, payment: OrderPayment) -> str:
        template = get_template('pretixplugins/banktransfer/control.html')
        ctx = {'request': request, 'event': self.event,
               'code': self._code(payment.order),
               'payment_info': payment.info_data, 'order': payment.order}
        return template.render(ctx)

    def _code(self, order):
        if self.settings.get('omit_hyphen', as_type=bool):
            return self.event.slug.upper() + order.code
        else:
            return order.full_code

    def shred_payment_info(self, obj):
        if not obj.info_data:
            return
        d = obj.info_data
        d['reference'] = '█'
        d['payer'] = '█'
        d['_shredded'] = True
        obj.info = json.dumps(d)
        obj.save(update_fields=['info'])
