#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django import forms
from django.utils.translation import gettext_lazy as _

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
