import json

from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.shredder import BaseDataShredder
from pretix.base.signals import (
    logentry_display, register_data_shredders, register_payment_providers,
    requiredaction_display,
)


@receiver(register_payment_providers, dispatch_uid="payment_paypal")
def register_payment_provider(sender, **kwargs):
    from .payment import Paypal
    return Paypal


@receiver(signal=logentry_display, dispatch_uid="paypal_logentry_display")
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    if logentry.action_type != 'pretix.plugins.paypal.event':
        return

    data = json.loads(logentry.data)
    event_type = data.get('event_type')
    text = None
    plains = {
        'PAYMENT.SALE.COMPLETED': _('Payment completed.'),
        'PAYMENT.SALE.DENIED': _('Payment denied.'),
        'PAYMENT.SALE.REFUNDED': _('Payment refunded.'),
        'PAYMENT.SALE.REVERSED': _('Payment reversed.'),
    }

    if event_type in plains:
        text = plains[event_type]

    if text:
        return _('PayPal reported an event: {}').format(text)


@receiver(signal=requiredaction_display, dispatch_uid="paypal_requiredaction_display")
def pretixcontrol_action_display(sender, action, request, **kwargs):
    if not action.action_type.startswith('pretix.plugins.paypal'):
        return

    data = json.loads(action.data)

    if action.action_type == 'pretix.plugins.paypal.refund':
        template = get_template('pretixplugins/paypal/action_refund.html')
    elif action.action_type == 'pretix.plugins.paypal.overpaid':
        template = get_template('pretixplugins/paypal/action_overpaid.html')
    elif action.action_type == 'pretix.plugins.paypal.double':
        template = get_template('pretixplugins/paypal/action_double.html')

    ctx = {'data': data, 'event': sender, 'action': action}
    return template.render(ctx, request)


class PaymentLogsShredder(BaseDataShredder):
    verbose_name = _('PayPal payment history')
    identifier = 'paypal_logs'
    description = _('This will remove payment-related history information. No download will be offered.')

    def generate_files(self):
        pass

    def shred_data(self):
        for le in self.event.logentry_set.filter(action_type="pretix.plugins.paypal.event").exclude(data=""):
            d = le.parsed_data
            if 'resource' in d:
                d['resource'] = {
                    'id': d['resource'].get('id'),
                    'sale_id': d['resource'].get('sale_id'),
                    'parent_payment': d['resource'].get('parent_payment'),
                }
            le.data = json.dumps(d)
            le.shredded = True
            le.save(update_fields=['data', 'shredded'])


@receiver(register_data_shredders, dispatch_uid="paypal_shredders")
def register_shredder(sender, **kwargs):
    return [
        PaymentLogsShredder,
    ]
