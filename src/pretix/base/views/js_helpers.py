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
import pycountry
from django.http import JsonResponse
from django.utils.translation import pgettext

from pretix.base.addressvalidation import (
    COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED,
)
from pretix.base.models.tax import VAT_ID_COUNTRIES
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, COUNTRY_STATE_LABEL,
)


def states(request):
    cc = request.GET.get("country", "DE")
    info = {
        'street': {'required': True},
        'zipcode': {'required': cc in COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED},
        'city': {'required': cc in COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED},
        'state': {
            'visible': cc in COUNTRIES_WITH_STATE_IN_ADDRESS,
            'required': cc in COUNTRIES_WITH_STATE_IN_ADDRESS,
            'label': COUNTRY_STATE_LABEL.get(cc, pgettext('address', 'State')),
        },
        'vat_id': {'visible': cc in VAT_ID_COUNTRIES, 'required': False},
    }
    if cc not in COUNTRIES_WITH_STATE_IN_ADDRESS:
        return JsonResponse({'data': [], **info, })
    types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
    statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
    return JsonResponse({
        'data': [
            {'name': s.name, 'code': s.code[3:]}
            for s in sorted(statelist, key=lambda s: s.name)
        ],
        **info,
    })
