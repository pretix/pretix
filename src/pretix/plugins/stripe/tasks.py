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
import logging
from urllib.parse import urlsplit

import stripe
from django.conf import settings

from pretix.base.services.tasks import EventTask
from pretix.celery_app import app
from pretix.multidomain.urlreverse import get_event_domain
from pretix.plugins.stripe.models import RegisteredApplePayDomain

logger = logging.getLogger(__name__)


def get_domain_for_event(event):
    domain = get_event_domain(event, fallback=True)
    if not domain:
        siteurlsplit = urlsplit(settings.SITE_URL)
        return siteurlsplit.hostname
    return domain


def get_stripe_account_key(prov):
    if prov.settings.connect_user_id:
        return prov.settings.connect_user_id
    else:
        return prov.settings.publishable_key


@app.task(base=EventTask, max_retries=5, default_retry_delay=1)
def stripe_verify_domain(event, domain):
    from pretix.plugins.stripe.payment import StripeCC
    prov = StripeCC(event)
    account = get_stripe_account_key(prov)

    # Yes, we could just use the **prov.api_kwargs
    # But since we absolutely need to always issue this call with live keys,
    # we're building our api_kwargs here by hand.
    # Only if no live connect secret key is set, we'll fall back to the testmode keys.
    # But this should never happen except in scenarios where pretix runs in devmode.
    if prov.settings.connect_client_id and prov.settings.connect_user_id:
        api_kwargs = {
            'api_key': prov.settings.connect_secret_key or prov.settings.connect_test_secret_key,
            'stripe_account': prov.settings.connect_user_id
        }
    else:
        api_kwargs = {
            'api_key': prov.settings.secret_key,
        }

    if RegisteredApplePayDomain.objects.filter(account=account, domain=domain).exists():
        return

    try:
        resp = stripe.ApplePayDomain.create(
            domain_name=domain,
            **api_kwargs
        )
    except stripe.error.StripeError:
        logger.exception('Could not verify domain with Stripe')
    else:
        if resp.livemode:
            RegisteredApplePayDomain.objects.create(
                domain=domain,
                account=account
            )
