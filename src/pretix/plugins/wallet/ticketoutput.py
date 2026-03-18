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


logger = logging.getLogger('pretix.plugins.wallet')


class WalletSettingsHolder(BaseTicketOutput):
    identifier = 'wallet'
    verbose_name = _('Wallet Output')
    
    is_meta = True
    is_enabled = False
    preview_allowed = False # TODO: implement own preview view or hide button for meta-outputs

class WalletOutput(BaseTicketOutput):
    settings_form_fields = []

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('ticketoutput', WalletSettingsHolder.identifier, event)

class GoogleWalletTicketOutput(WalletOutput):
    identifier = 'wallet_google'
    verbose_name = _('Google')
    download_button_text = "Add to Google Wallet"

class AppleWalletTicketOutput(WalletOutput):
    identifier = 'wallet_apple'
    verbose_name = _('Apple')
    download_button_text = "Add to Apple Wallet"

OUTPUTS = [WalletSettingsHolder, GoogleWalletTicketOutput, AppleWalletTicketOutput]
