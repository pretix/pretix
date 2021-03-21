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
import stripe
from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled

from pretix.base.models import Event
from pretix.base.settings import GlobalSettingsObject


class Command(BaseCommand):
    help = "Detect country for Stripe Connect accounts connected with pretix 2.0 (required for payment request buttons)"

    @scopes_disabled()
    def handle(self, *args, **options):
        cache = {}
        gs = GlobalSettingsObject()
        api_key = gs.settings.payment_stripe_connect_secret_key or gs.settings.payment_stripe_connect_test_secret_key
        if not api_key:
            self.stderr.write(self.style.ERROR("Stripe Connect is not set up!"))
            return

        for e in Event.objects.filter(plugins__icontains="pretix.plugins.stripe"):
            uid = e.settings.payment_stripe_connect_user_id
            if uid and not e.settings.payment_stripe_merchant_country:
                if uid in cache:
                    e.settings.payment_stripe_merchant_country = cache[uid]
                else:
                    try:
                        account = stripe.Account.retrieve(
                            uid,
                            api_key=api_key
                        )
                    except Exception as e:
                        print(e)
                    else:
                        e.settings.payment_stripe_merchant_country = cache[uid] = account.get('country')
