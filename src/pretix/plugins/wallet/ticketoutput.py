#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from django.utils.translation import gettext_lazy as _
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.base.models import Event
from pretix.base.settings import SettingsSandbox
from django.template.loader import render_to_string

from .styles import AVAILABLE_STYLES_DICT
from .styles.apple import ApplePlatform
from .styles.google import GooglePlatform

from .models import WalletLayout
from .views import get_layout_variables


logger = logging.getLogger("pretix.plugins.wallet")


class WalletSettingsHolder(BaseTicketOutput):
    identifier = "wallet"
    verbose_name = _("Wallet Output")

    is_meta = True
    is_enabled = False
    preview_allowed = (
        False  # TODO: implement own preview view or hide button for meta-outputs
    )

    def settings_content_render(self, request) -> str:
        return render_to_string(
            "pretixplugins/wallet/settings_content.html", {"request": request}
        )


class WalletOutput(BaseTicketOutput):
    settings_form_fields = []

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox(
            "ticketoutput", WalletSettingsHolder.identifier, event
        )


class GoogleWalletTicketOutput(WalletOutput):
    identifier = "wallet_google"
    verbose_name = _("Google")
    download_button_text = "Add to Google Wallet"
    platform = GooglePlatform


class AppleWalletTicketOutput(WalletOutput):
    identifier = "wallet_apple"
    verbose_name = _("Apple")
    download_button_text = "Add to Apple Wallet"
    platform = ApplePlatform

    def generate(self, op):
        order = op.order
        event = order.event
        filename = "{}-{}.pkpass".format(order.event.slug, order.code)

        # layout = self.override_layout_signal.send_chained(
        #     order.event, 'layout', orderposition=op, layout=self.layout_map.get(
        #         (op.item_id, self.override_channel or order.sales_channel.identifier),
        #         self.layout_map.get(
        #             (op.item_id, 'web'),
        #             self.default_layout
        #         )
        #     )
        # )
        layout = WalletLayout.objects.get(pk=1)
        platform_layout = layout.platform_layouts.get(platform=self.platform.identifier)

        ticket = str(op.item.name)
        if op.variation:
            ticket += " - " + str(op.variation)
        
        serialNumber = "%s-%s-%s-%d" % (
            order.event.organizer.slug,
            order.event.slug,
            order.code,
            op.pk,
        )

        context = {
            "placeholders": get_layout_variables(op.order.event),
            "evaluation_context": [op, order, order.event],
            "ca_certificate": open(
                "/Users/engelhardt/code/tmp/wallet/apple/ca_cert.pem", "rb"
            ).read(),
            "certificate": open(
                "/Users/engelhardt/code/tmp/wallet/apple/cert.pem", "rb"
            ).read(),
            "key": open(
                "/Users/engelhardt/code/tmp/wallet/apple/secret_key.pem", "rb"
            ).read(),
            "password": None,
            "description": _("Ticket for {event} ({product})").format( # TODO: i18n
                event=event.name, product=ticket
            ),
            "organizationName": event.organizer.name,
            "passTypeIdentifier": "pass.test.test",
            "teamIdentifier": "TEST123456",
            "serialNumber": serialNumber,
            "locales": event.settings.locales
        }

        data = AVAILABLE_STYLES_DICT[self.platform.identifier][platform_layout.style].generate(
            platform_layout.layout, context
        )
        return filename, "application/vnd.apple.pkpass", data


OUTPUTS = [WalletSettingsHolder, GoogleWalletTicketOutput, AppleWalletTicketOutput]
