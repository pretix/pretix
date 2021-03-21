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
from decimal import Decimal

from django.conf import settings
from django.core.validators import DecimalValidator
from django.forms import NumberInput, TextInput
from django.utils import formats


class DecimalTextInput(TextInput):
    def __init__(self, *args, **kwargs):
        self.places = kwargs.pop('places', 2)
        super().__init__(*args, **kwargs)

    def format_value(self, value):
        """
        Return a value as it should appear when rendered in a template.
        """
        if value == '' or value is None:
            return None
        if isinstance(value, str):
            return value
        if not isinstance(value, Decimal):
            value = Decimal(value)
        return formats.localize_input(value.quantize(Decimal('1') / 10 ** self.places))


def change_decimal_field(field, currency):
    places = settings.CURRENCY_PLACES.get(currency, 2)
    field.decimal_places = places
    field.localize = True
    if isinstance(field.widget, NumberInput):
        field.widget.attrs['step'] = str(Decimal('1') / 10 ** places).lower()
    elif isinstance(field.widget, TextInput):
        field.widget = DecimalTextInput(places=places)
    v = [v for v in field.validators if isinstance(v, DecimalValidator)]
    if len(v) == 1:
        v[0].decimal_places = places
