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
from django.shortcuts import get_object_or_404
from .styles import AVAILABLE_STYLES_DICT
from .styles.base import PassLayout, WalletPlatform
from .styles.apple import ApplePlatform
from .styles.google import GooglePlatform
from collections import OrderedDict
from .models import WalletLayout
from .views import get_layout_variables
from django import forms
from .forms import CertificateFileField, validate_rsa_privkey
from pretix.control.forms import ClearableBasenameFileInput

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
    platform: WalletPlatform

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox(
            "ticketoutput", WalletSettingsHolder.identifier, event
        )

    def generate(self, op):
        if hasattr(op.item, "walletlayout"):
            wallet_layout = op.item.walletlayout
        else:
            wallet_layout = op.event.wallet_layouts.get(default=True)
        platform_layout = get_object_or_404(wallet_layout.platform_layouts, platform=self.platform.identifier)
        return self.platform.generate(platform_layout.pass_layout, op)


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

    def get_global_settings(sender, **kwargs):
        return OrderedDict(
            [
                (
                    "wallet_apple_team_id",
                    forms.CharField(
                        label=_("Apple Wallet Pass team ID"),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_pass_type_id",
                    forms.CharField(
                        label=_("Apple Wallet Pass type"),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_certificate",
                    CertificateFileField(
                        label=_("Apple Wallet Pass certificate file"),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_ca_certificate",
                    CertificateFileField(
                        label=_("Apple Wallet Pass CA Certificate"),
                        help_text=_(
                            "You can download the current CA certificate from apple at "
                            "https://www.apple.com/certificateauthority/AppleWWDRCAG4.cer"
                        ),
                        required=False,
                    ),
                ),
                (
                    "wallet_apple_key",
                    forms.FileField(
                        label=_("Apple Wallet Pass secret key"),
                        required=False,
                        validators=[validate_rsa_privkey],
                        widget=ClearableBasenameFileInput
                    ),
                ),
                (
                    "wallet_apple_key_password",
                    forms.CharField(
                        label=_("Apple Wallet Pass key password"),
                        widget=forms.PasswordInput(render_value=True),
                        required=False,
                        help_text=_(
                            "Optional, only necessary if the key entered above requires a password to use."
                        ),
                    ),
                ),
            ]
        )


# settings_hierarkey.add_default("wallet_apple_certificate_file", None, File)
# settings_hierarkey.add_default("wallet_apple_wwdr_certificate_file", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_background", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_background2x", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_background3x", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_icon", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_icon2x", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_icon3x", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_logo", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_logo2x", None, File)
# settings_hierarkey.add_default("ticketoutput_wallet_apple_logo3x", None, File)

OUTPUTS = [WalletSettingsHolder, GoogleWalletTicketOutput, AppleWalletTicketOutput]
