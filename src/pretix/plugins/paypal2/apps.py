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

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class Paypal2App(AppConfig):
    name = 'pretix.plugins.paypal2'
    verbose_name = "PayPal"

    class PretixPluginMeta:
        name = "PayPal"
        author = _("the pretix team")
        version = version
        category = 'PAYMENT'
        featured = True
        picture = 'pretixplugins/paypal2/paypal_logo.svg'
        description = _("Accept payments with your PayPal account. In addition to regular PayPal payments, you can now "
                        "also offer payments in a variety of local payment methods such as giropay, SOFORT, iDEAL and "
                        "many more to your customers - they don't even need a PayPal account. PayPal is one of the "
                        "most popular payment methods world-wide.")

    def ready(self):
        from . import signals  # NOQA

    def is_available(self, event):
        return 'pretix.plugins.paypal' not in event.plugins.split(',')
