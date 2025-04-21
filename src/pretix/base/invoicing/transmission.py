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
from django import forms
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

    def is_available(self, country: Country, is_business: bool):
        raise NotImplementedError

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
            "transmission_email_to_order": forms.BooleanField(
                label=_("Send invoice to order email address"),
                required=False,
            ),
            "transmission_email_address": forms.EmailField(
                label=_("Email address for invoice"),
                widget=forms.EmailInput(
                    attrs={"data-inverse-dependency": "#id_transmission_email_address"}
                )
            )
        }


class ItalianSdITransmissionType(TransmissionType):
    identifier = "it_sdi"
    verbose_name = pgettext_lazy("italian_invoice", "Exchange System (SdI)")

    def is_available(self, country: Country, is_business: bool):
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
                label=pgettext_lazy("italian_invoice", "Address for certified email"),
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


TRANSMISSION_TYPES = [
    EmailTransmissionType,
    ItalianSdITransmissionType,
]
