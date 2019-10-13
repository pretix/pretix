from django import forms
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import SettingsForm


class StripeKeyValidator:
    def __init__(self, prefix):
        assert len(prefix) > 0
        if isinstance(prefix, list):
            self._prefixes = prefix
        else:
            self._prefixes = [prefix]
            assert isinstance(prefix, str)

    def __call__(self, value):
        if not any(value.startswith(p) for p in self._prefixes):
            raise forms.ValidationError(
                _('The provided key "%(value)s" does not look valid. It should start with "%(prefix)s".'),
                code='invalid-stripe-key',
                params={
                    'value': value,
                    'prefix': self._prefixes[0],
                },
            )


class OrganizerStripeSettingsForm(SettingsForm):
    payment_stripe_connect_app_fee_percent = forms.DecimalField(
        label=_('Stripe Connect: App fee (percent)'),
        required=False,
    )
    payment_stripe_connect_app_fee_max = forms.DecimalField(
        label=_('Stripe Connect: App fee (max)'),
        required=False,
    )
    payment_stripe_connect_app_fee_min = forms.DecimalField(
        label=_('Stripe Connect: App fee (min)'),
        required=False,
    )
