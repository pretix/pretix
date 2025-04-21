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
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django_countries.fields import Country
from django_scopes import scope

from pretix.base.addressvalidation import (
    COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED,
)
from pretix.base.invoicing.transmission import TRANSMISSION_TYPES
from pretix.base.models import Organizer
from pretix.base.models.tax import VAT_ID_COUNTRIES
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, COUNTRY_STATE_LABEL,
)


def _info(cc):
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
        return {'data': [], **info}
    types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[cc]
    statelist = [s for s in pycountry.subdivisions.get(country_code=cc) if s.type in types]
    return {
        'data': [
            {'name': s.name, 'code': s.code[3:]}
            for s in sorted(statelist, key=lambda s: s.name)
        ],
        **info,
    }


def address_form(request):
    cc = request.GET.get("country", "DE")
    info = _info(cc)

    if request.GET.get("invoice") == "true":
        # Do not consider live=True, as this does not expose sensitive information and we also want it accessible
        # from e.g. the backend when the event is not yet life.
        organizer = get_object_or_404(Organizer, slug=request.GET.get("organizer"))
        with scope(organizer=organizer):
            event = get_object_or_404(organizer.events, slug=request.GET.get("event"))
            country = Country(cc)
            is_business = request.GET.get("is_business") == "business"
            selected_transmission_type = request.GET.get("transmission_type")

            info["transmission_type"] = {
                "visible": True,
            }
            info["transmission_types"] = [
                {'name': str(t.public_name), 'code': t.identifier}
                for t in TRANSMISSION_TYPES if t.is_available(
                    event=event,
                    country=country,
                    is_business=is_business
                )
            ]
            if selected_transmission_type not in [t["code"] for t in info["transmission_types"]]:
                # The previously selected transmission type is no longer selectable, e.g. because
                # of a country change. To avoid a second roundtrip to this endpoint, let's show
                # the fields as if the first remaining option were selected (which is what the client
                # side will now do).
                selected_transmission_type = info["transmission_types"][0]["code"]

            for transmission_type in TRANSMISSION_TYPES:
                required = transmission_type.invoice_address_form_fields_required(
                    country=country,
                    is_business=is_business
                )
                if transmission_type.identifier == selected_transmission_type:
                    for k, v in info.items():
                        if k in required:
                            v["required"] = True
                for k, f in transmission_type.invoice_address_form_fields.items():
                    info[k] = {
                        "visible": transmission_type.identifier == selected_transmission_type,
                        "required": transmission_type.identifier == selected_transmission_type and k in required
                    }

    return JsonResponse(info)
