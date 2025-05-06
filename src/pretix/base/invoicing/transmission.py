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
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_countries.fields import Country
from localflavor.it.forms import ITSocialSecurityNumberField

from pretix.base.models import InvoiceAddress


class TransmissionType:
    @property
    def identifier(self):
        raise NotImplementedError

    @property
    def verbose_name(self):
        raise NotImplementedError

    @property
    def public_name(self):
        return self.verbose_name

    def is_available(self, event, country: Country, is_business: bool):
        raise NotImplementedError

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        return set()

    def validate_address(self, ia: InvoiceAddress):
        pass

    @property
    def invoice_address_form_fields(self) -> dict:
        """
        Return a set of form fields that **must** be prefixed with ``transmission_<identifier>_``.
        """
        return {}


class EmailTransmissionType(TransmissionType):
    identifier = "email"
    verbose_name = _("Email")

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_email_other": forms.BooleanField(
                label=_("Send invoice directly to accounting department"),
                help_text=_("If not selected, the invoice will be sent to you using the email address listed above."),
                required=False,
            ),
            "transmission_email_address": forms.EmailField(
                label=_("Email address for invoice"),
                widget=forms.EmailInput(
                    attrs={"data-display-dependency": "#id_transmission_email_other"}
                )
            )
        }

    def is_available(self, event, country: Country, is_business: bool):
        return str(country) != "IT"  # todo: fixme


class ItalianSdITransmissionType(TransmissionType):
    identifier = "it_sdi"
    verbose_name = pgettext_lazy("italian_invoice", "Exchange System (SdI)")

    def is_available(self, event, country: Country, is_business: bool):
        # TODO: only when a matching provider is installed
        # or make it a setting?
        return str(country) == "IT"

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_it_sdi_codice_fiscale": ITSocialSecurityNumberField(
                label=pgettext_lazy("italian_invoice", "Fiscal code"),
                required=False,
            ),
            "transmission_it_sdi_pec": forms.EmailField(
                label=pgettext_lazy("italian_invoice", "Address for certified electronical mail"),
                widget=forms.EmailInput(
                    attrs={"data-inverse-dependency": "#id_transmission_email_address"}
                )
            ),
            "transmission_it_sdi_recipient_code": forms.CharField(
                label=pgettext_lazy("italian_invoice", "Recipient code"),
                validators=[
                    RegexValidator("^[A-Z0-9]{7}$")
                ]
            ),
        }

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        if is_business:
            return {"vat_id", "transmission_it_sdi_pec", "transmission_it_sdi_recipient_code"}
        return {"transmission_it_sdi_codice_fiscale"}


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
        "0208": "0[0-9]{9}",
        "0209": ".*",
        "0210": "[A-Z0-9]+",
        "0211": "IT[0-9]{11}",
        "0212": "[0-9]{7}-[0-9]",
        "0213": "FI[0-9]{8}",
        "0205": "[A-Z0-9]+",
        "0221": "T[0-9]{13}",
        "0230": ".*",
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
        "9954": ".*",
        "9956": "0[0-9]{9}",
        "9957": ".*",
        "9959": ".*",
    }

    def __call__(self, value):
        if ":" not in value:
            raise ValidationError(_("A PEPPOL participant ID always starts with a prefix, followed by a colon (:)."))

        prefix, second = value.split(":", 1)
        if prefix not in self.regex_rules:
            raise ValidationError(_("The PEPPOL participant ID prefix %(number)s is not known to our system. Please "
                                    "reach out to us if you are sure this ID is correct."), params={"number": prefix})

        if not re.match(self.regex_rules[prefix], second):
            raise ValidationError(_("The PEPPOL participant ID does not match the validation rules for the prefix "
                                    "%(number)s. Please reach out to us if you are sure this ID is correct."),
                                  params={"number": prefix})
        return value


class PeppolTransmissionType(TransmissionType):
    identifier = "peppol"
    verbose_name = "PEPPOL"

    def is_available(self, event, country: Country, is_business: bool):
        # TODO: only when a matching provider is installed
        # or make it a setting?
        return is_business

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_peppol_participant_id": forms.CharField(
                label=_("PEPPOL participant ID"),
                validators=[
                    PeppolIdValidator(),
                ]
            ),
        }

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        return {"transmission_peppol_participant_id"}


TRANSMISSION_TYPES = [
    EmailTransmissionType(),
    ItalianSdITransmissionType(),
    PeppolTransmissionType(),
]
