import json

from django.core.urlresolvers import resolve
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import ugettext_lazy as _

from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    logentry_display, register_payment_providers, requiredaction_display,
)
from pretix.presale.signals import html_head


@receiver(register_payment_providers, dispatch_uid="payment_stripe")
def register_payment_provider(sender, **kwargs):
    from .payment import (
        StripeSettingsHolder, StripeCC, StripeGiropay, StripeIdeal, StripeAlipay, StripeBancontact,
        StripeSofort
    )

    return [StripeSettingsHolder, StripeCC, StripeGiropay, StripeIdeal, StripeAlipay, StripeBancontact, StripeSofort]


@receiver(html_head, dispatch_uid="payment_stripe_html_head")
def html_head_presale(sender, request=None, **kwargs):
    from .payment import StripeSettingsHolder

    provider = StripeSettingsHolder(sender)
    url = resolve(request.path_info)
    if provider.settings.get('_enabled', as_type=bool) and ("checkout" in url.url_name or "order.pay" in url.url_name):
        template = get_template('pretixplugins/stripe/presale_head.html')
        ctx = {'event': sender, 'settings': provider.settings}
        return template.render(ctx)
    else:
        return ""


@receiver(signal=logentry_display, dispatch_uid="stripe_logentry_display")
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    if logentry.action_type != 'pretix.plugins.stripe.event':
        return

    data = json.loads(logentry.data)
    event_type = data.get('type')
    text = None
    plains = {
        'charge.succeeded': _('Charge succeeded.'),
        'charge.refunded': _('Charge refunded.'),
        'charge.updated': _('Charge updated.'),
        'charge.pending': _('Charge pending'),
        'source.chargeable': _('Payment authorized.'),
        'source.canceled': _('Payment authorization canceled.'),
        'source.failed': _('Payment authorization failed.')
    }

    if event_type in plains:
        text = plains[event_type]
    elif event_type == 'charge.failed':
        text = _('Charge failed. Reason: {}').format(data['data']['object']['failure_message'])
    elif event_type == 'charge.dispute.created':
        text = _('Dispute created. Reason: {}').format(data['data']['object']['reason'])
    elif event_type == 'charge.dispute.updated':
        text = _('Dispute updated. Reason: {}').format(data['data']['object']['reason'])
    elif event_type == 'charge.dispute.closed':
        text = _('Dispute closed. Status: {}').format(data['data']['object']['status'])

    if text:
        return _('Stripe reported an event: {}').format(text)


@receiver(signal=requiredaction_display, dispatch_uid="stripe_requiredaction_display")
def pretixcontrol_action_display(sender, action, request, **kwargs):
    if not action.action_type.startswith('pretix.plugins.stripe'):
        return

    data = json.loads(action.data)

    if action.action_type == 'pretix.plugins.stripe.refund':
        template = get_template('pretixplugins/stripe/action_refund.html')
    elif action.action_type == 'pretix.plugins.stripe.overpaid':
        template = get_template('pretixplugins/stripe/action_overpaid.html')

    ctx = {'data': data, 'event': sender, 'action': action}
    return template.render(ctx, request)


settings_hierarkey.add_default('payment_stripe_method_cc', True, bool)
