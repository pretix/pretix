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
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _


class BaseMediaType:
    medium_created_by_server = False
    supports_orderposition = False
    supports_giftcard = False

    @property
    def identifier(self):
        raise NotImplementedError()

    @property
    def verbose_name(self):
        raise NotImplementedError()

    def generate_identifier(self, organizer):
        if self.medium_created_by_server:
            raise NotImplementedError()
        else:
            raise ValueError("Media type does not allow to generate identifier")

    def is_active(self, organizer):
        return organizer.settings.get(f'reusable_media_type_{self.identifier}_active', as_type=bool, default=False)

    def __str__(self):
        return str(self.verbose_name)


class BarcodePlainMediaType(BaseMediaType):
    identifier = 'barcode'
    verbose_name = _('Barcode / QR-Code')
    medium_created_by_server = True
    supports_giftcard = False
    supports_orderposition = True

    def generate_identifier(self, organizer):
        return get_random_string(
            length=organizer.settings.reusable_media_type_barcode_identifier_length,
            # Exclude o,0,1,i to avoid confusion with bad fonts/printers
            # We use upper case to make collisions with ticket secrets less likely
            allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        )


class NtagPasswordPretix1MediaType(BaseMediaType):
    identifier = 'ntag_password_pretix1'
    verbose_name = _('NFC NTAG (pretix scheme 1)')
    medium_created_by_server = False
    supports_giftcard = True
    supports_orderposition = False


MEDIA_TYPES = {
    m.identifier: m for m in [
        BarcodePlainMediaType(),
        NtagPasswordPretix1MediaType(),
    ]
}
