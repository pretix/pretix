import json
from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve
from django.utils.translation import ugettext_lazy as _

from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    logentry_display, register_global_settings, register_payment_providers,
    requiredaction_display,
)
from pretix.plugins.stripe.forms import StripeKeyValidator
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
        ctx = {
            'event': sender,
            'settings': provider.settings,
            'testmode': (
                (provider.settings.get('endpoint', 'live') == 'test' or sender.testmode)
                and provider.settings.publishable_test_key
            )
        }
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


settings_hierarkey.add_default('payment_stripe_method_cc', True, bool)
settings_hierarkey.add_default('payment_stripe_cc_3ds_mode', 'recommended', str)


@receiver(register_global_settings, dispatch_uid='stripe_global_settings')
def register_global_settings(sender, **kwargs):
    return OrderedDict([
        ('payment_stripe_connect_client_id', forms.CharField(
            label=_('Stripe Connect: Client ID'),
            required=False,
            validators=(
                StripeKeyValidator('ca_'),
            ),
        )),
        ('payment_stripe_connect_secret_key', forms.CharField(
            label=_('Stripe Connect: Secret key'),
            required=False,
            validators=(
                StripeKeyValidator(['sk_live_', 'rk_live_']),
            ),
        )),
        ('payment_stripe_connect_publishable_key', forms.CharField(
            label=_('Stripe Connect: Publishable key'),
            required=False,
            validators=(
                StripeKeyValidator('pk_live_'),
            ),
        )),
        ('payment_stripe_connect_test_secret_key', forms.CharField(
            label=_('Stripe Connect: Secret key (test)'),
            required=False,
            validators=(
                StripeKeyValidator(['sk_test_', 'rk_test_']),
            ),
        )),
        ('payment_stripe_connect_test_publishable_key', forms.CharField(
            label=_('Stripe Connect: Publishable key (test)'),
            required=False,
            validators=(
                StripeKeyValidator('pk_test_'),
            ),
        )),
    ])


@receiver(signal=requiredaction_display, dispatch_uid="stripe_requiredaction_display")
def pretixcontrol_action_display(sender, action, request, **kwargs):
    # DEPRECATED
    if not action.action_type.startswith('pretix.plugins.stripe'):
        return

    data = json.loads(action.data)

    if action.action_type == 'pretix.plugins.stripe.refund':
        template = get_template('pretixplugins/stripe/action_refund.html')
    elif action.action_type == 'pretix.plugins.stripe.overpaid':
        template = get_template('pretixplugins/stripe/action_overpaid.html')
    elif action.action_type == 'pretix.plugins.stripe.double':
        template = get_template('pretixplugins/stripe/action_double.html')

    ctx = {'data': data, 'event': sender, 'action': action}
    return template.render(ctx, request)
