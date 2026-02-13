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
import base64
import hashlib
import re

import dns.resolver
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _, pgettext
from django_countries.fields import Country

from pretix.base.invoicing.transmission import (
    TransmissionType, transmission_types,
)


class PeppolIdValidator:
    regex_rules = {
        # Source: https://docs.peppol.eu/edelivery/codelists/old/v8.5/Peppol%20Code%20Lists%20-%20Participant%20identifier%20schemes%20v8.5.html
        "0002": "[0-9]{9}([0-9]{5})?",
        "0007": "[0-9]{10}",
        "0009": "[0-9]{14}",
        "0037": "(0037)?[0-9]{7}-?[0-9][0-9A-Z]{0,5}",
        "0060": "[0-9]{9}",
        "0088": "[0-9]{13}",
        "0096": "[0-9]{17}",
        "0097": "[0-9]{11,16}",
        "0106": "[0-9]{17}",
        "0130": ".*",
        "0135": ".*",
        "0142": ".*",
        "0151": "[0-9]{11}",
        "0183": "CHE[0-9]{9}",
        "0184": "DK[0-9]{8}([0-9]{2})?",
        "0188": ".*",
        "0190": "[0-9]{20}",
        "0191": "[1789][0-9]{7}",
        "0192": "[0-9]{9}",
        "0193": ".{4,50}",
        "0195": "[a-z]{2}[a-z]{3}([0-9]{8}|[0-9]{9}|[RST][0-9]{2}[a-z]{2}[0-9]{4})[0-9a-z]",
        "0196": "[0-9]{10}",
        "0198": "DK[0-9]{8}",
        "0199": "[A-Z0-9]{18}[0-9]{2}",
        "0020": "[0-9]{9}",
        "0201": "[0-9a-zA-Z]{6}",
        "0204": "[0-9]{2,12}(-[0-9A-Z]{0,30})?-[0-9]{2}",
        "0208": "[01][0-9]{9}",
        "0209": ".*",
        "0210": "[A-Z0-9]+",
        "0211": "IT[0-9]{11}",
        "0212": "[0-9]{7}-[0-9]",
        "0213": "FI[0-9]{8}",
        "0205": "[A-Z0-9]+",
        "0221": "T[0-9]{13}",
        "0230": ".*",
        "0244": "[0-9]{13}",
        "0245": "[0-9]{10}",
        "0246": "DE[0-9]{9}(-[0-9]{5})?(\\.[0-9A-Z]{1,8})?",
        "9901": ".*",
        "9902": "[1-9][0-9]{7}",
        "9904": "DK[0-9]{8}",
        "9909": "NO[0-9]{9}MVA",
        "9910": "HU[0-9]{8}",
        "9912": "[A-Z]{2}[A-Z0-9]{,20}",
        "9913": ".*",
        "9914": "ATU[0-9]*",
        "9915": "[A-Z][A-Z0-9]*",
        "9916": ".*",
        "9917": "[0-9]{10}",
        "9918": "[A-Z]{2}[0-9]{2}[A-Z-0-9]{11,30}",
        "9919": "[A-Z][0-9]{3}[A-Z][0-9]{3}[A-Z]",
        "9920": ".*",
        "9921": ".*",
        "9922": ".*",
        "9923": ".*",
        "9924": ".*",
        "9925": ".*",
        "9926": ".*",
        "9927": ".*",
        "9928": ".*",
        "9929": ".*",
        "9930": ".*",
        "9931": ".*",
        "9932": ".*",
        "9933": ".*",
        "9934": ".*",
        "9935": ".*",
        "9936": ".*",
        "9937": ".*",
        "9938": ".*",
        "9939": ".*",
        "9940": ".*",
        "9941": ".*",
        "9942": ".*",
        "9943": ".*",
        "9944": ".*",
        "9945": ".*",
        "9946": ".*",
        "9947": ".*",
        "9948": ".*",
        "9949": ".*",
        "9950": ".*",
        "9951": ".*",
        "9952": ".*",
        "9953": ".*",
        "9956": "0[0-9]{9}",
        "9957": ".*",
        "9959": ".*",
    }

    def __init__(self, validate_online=False):
        self.validate_online = validate_online

    def __call__(self, value):
        if ":" not in value:
            raise ValidationError(_("A Peppol participant ID always starts with a prefix, followed by a colon (:)."))

        prefix, second = value.split(":", 1)
        if prefix not in self.regex_rules:
            raise ValidationError(_("The Peppol participant ID prefix %(number)s is not known to our system. Please "
                                    "reach out to us if you are sure this ID is correct."), params={"number": prefix})

        if not re.match(self.regex_rules[prefix], second):
            raise ValidationError(_("The Peppol participant ID does not match the validation rules for the prefix "
                                    "%(number)s. Please reach out to us if you are sure this ID is correct."),
                                  params={"number": prefix})

        if self.validate_online:
            base_hostnames = ['edelivery.tech.ec.europa.eu', 'acc.edelivery.tech.ec.europa.eu']
            smp_id = base64.b32encode(hashlib.sha256(value.lower().encode()).digest()).decode().rstrip("=")
            for base_hostname in base_hostnames:
                smp_domain = f'{smp_id}.iso6523-actorid-upis.{base_hostname}'
                resolver = dns.resolver.Resolver()
                try:
                    answers = resolver.resolve(smp_domain, 'NAPTR', lifetime=1.0)
                    if answers:
                        return value
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    # ID not registered, do not set found=True
                    pass
                except Exception:  # noqa
                    # Error likely on our end or infrastructure is down, allow user to proceed
                    return value

            raise ValidationError(
                _("The Peppol participant ID is not registered on the Peppol network."),
            )

        return value


@transmission_types.new()
class PeppolTransmissionType(TransmissionType):
    identifier = "peppol"
    verbose_name = "Peppol"
    priority = 250
    enforce_transmission = True

    def is_available(self, event, country: Country, is_business: bool):
        return is_business and super().is_available(event, country, is_business)

    def is_exclusive(self, event, country: Country, is_business: bool) -> bool:
        if is_business and str(country) == "BE" and event and event.settings.invoice_address_from_country == "BE":
            # Peppol is required to be used for intra-Belgian B2B invoices
            return True
        return False

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_peppol_participant_id": forms.CharField(
                label=_("Peppol participant ID"),
                validators=[
                    PeppolIdValidator(
                        validate_online=True,
                    ),
                ]
            ),
        }

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        base = {
            "company", "street", "zipcode", "city", "country",
        }
        return base | {"transmission_peppol_participant_id"}

    def pdf_watermark(self) -> str:
        return pgettext("peppol_invoice", "Visual copy")

    def pdf_info_text(self) -> str:
        return pgettext(
            "peppol_invoice",
            "This PDF document is a visual copy of the invoice and does not constitute an invoice for VAT "
            "purposes. The original invoice is issued in XML format and transmitted through the Peppol network."
        )
