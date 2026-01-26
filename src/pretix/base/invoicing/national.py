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

from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import pgettext, pgettext_lazy
from django_countries.fields import Country
from localflavor.it.forms import ITSocialSecurityNumberField

from pretix.base.invoicing.transmission import (
    TransmissionType, transmission_types,
)


@transmission_types.new()
class ItalianSdITransmissionType(TransmissionType):
    identifier = "it_sdi"
    verbose_name = pgettext_lazy("italian_invoice", "Italian Exchange System (SdI)")
    public_name = pgettext_lazy("italian_invoice", "Exchange System (SdI)")
    enforce_transmission = True

    def is_exclusive(self, event, country: Country, is_business: bool) -> bool:
        return str(country) == "IT"

    def is_available(self, event, country: Country, is_business: bool):
        return str(country) == "IT" and super().is_available(event, country, is_business)

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_it_sdi_codice_fiscale": ITSocialSecurityNumberField(
                label=pgettext_lazy("italian_invoice", "Fiscal code"),
                required=False,
            ),
            "transmission_it_sdi_pec": forms.EmailField(
                label=pgettext_lazy("italian_invoice", "Address for certified electronic mail"),
                widget=forms.EmailInput()
            ),
            "transmission_it_sdi_recipient_code": forms.CharField(
                label=pgettext_lazy("italian_invoice", "Recipient code"),
                validators=[
                    RegexValidator("^[A-Z0-9]{6,7}$")
                ]
            ),
        }

    def invoice_address_form_fields_visible(self, country: Country, is_business: bool):
        if is_business:
            return {"transmission_it_sdi_codice_fiscale", "transmission_it_sdi_pec", "transmission_it_sdi_recipient_code"}
        return {"transmission_it_sdi_codice_fiscale", "transmission_it_sdi_pec"}

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        base = {
            "street", "zipcode", "city", "state", "country",
        }
        if is_business:
            return base | {"company", "vat_id", "transmission_it_sdi_pec", "transmission_it_sdi_recipient_code"}
        return base | {"transmission_it_sdi_codice_fiscale"}

    def pdf_info_text(self) -> str:
        # Watermark is not necessary as this is a usual precaution in Italy
        return pgettext(
            "italian_invoice",
            "This PDF document is a visual copy of the invoice and does not constitute an invoice for VAT "
            "purposes. The invoice is issued in XML format, transmitted in accordance with the procedures and terms "
            "set forth in No. 89757/2018 of April 30, 2018, issued by the Director of the Revenue Agency."
        )
