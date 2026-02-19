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
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_countries.fields import Country
from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.invoicing.transmission import (
    TransmissionProvider, TransmissionType, transmission_providers,
    transmission_types,
)
from pretix.base.models import Invoice, InvoiceAddress
from pretix.base.services.mail import mail, render_mail
from pretix.helpers.format import format_map


@transmission_types.new()
class EmailTransmissionType(TransmissionType):
    identifier = "email"
    verbose_name = _("Email")
    priority = 1000

    @property
    def invoice_address_form_fields(self) -> dict:
        return {
            "transmission_email_other": forms.BooleanField(
                label=_("Email invoice directly to accounting department"),
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

    def invoice_address_form_fields_visible(self, country: Country, is_business: bool):
        if is_business:
            # We don't want ask non-business users if they have an accounting department ;)
            return {"transmission_email_other", "transmission_email_address"}
        return set()

    def is_available(self, event, country: Country, is_business: bool):
        # Skip availability check since provider is always available and we do not want to end up without invoice
        # transmission type
        return True

    def transmission_info_to_form_data(self, transmission_info: dict) -> dict:
        return {
            "transmission_email_other": bool(transmission_info.get("transmission_email_address")),
            "transmission_email_address": transmission_info.get("transmission_email_address"),
        }

    def form_data_to_transmission_info(self, form_data: dict) -> dict:
        if form_data.get("is_business") and form_data.get("transmission_email_other") and form_data.get("transmission_email_address"):
            return {
                "transmission_email_address": form_data["transmission_email_address"],
            }
        return {}


@transmission_providers.new()
class EmailTransmissionProvider(TransmissionProvider):
    identifier = "email_pdf"
    type = "email"
    verbose_name = _("PDF via email")
    priority = 1000
    testmode_supported = True

    def is_ready(self, event) -> bool:
        return True

    def is_available(self, event, country: Country, is_business: bool) -> bool:
        return True

    def transmit(self, invoice: Invoice):
        info = (invoice.invoice_to_transmission_info or {})
        if info.get("transmission_email_address"):
            recipient = info["transmission_email_address"]
        else:
            recipient = invoice.order.email

        if not recipient:
            invoice.transmission_status = Invoice.TRANSMISSION_STATUS_FAILED
            invoice.transmission_date = now()
            invoice.save(update_fields=["transmission_status", "transmission_date"])
            invoice.order.log_action(
                "pretix.event.order.invoice.sending_failed",
                data={
                    "full_invoice_no": invoice.full_invoice_no,
                    "transmission_provider": "email_pdf",
                    "transmission_type": "email",
                    "data": {
                        "reason": "no_recipient",
                    },
                }
            )
            return

        with language(invoice.order.locale, invoice.order.event.settings.region):
            context = get_email_context(
                event=invoice.order.event,
                order=invoice.order,
                invoice=invoice,
                event_or_subevent=invoice.order.event,
                invoice_address=getattr(invoice.order, 'invoice_address', None) or InvoiceAddress()
            )
            template = invoice.order.event.settings.get('mail_text_order_invoice', as_type=LazyI18nString)
            subject = invoice.order.event.settings.get('mail_subject_order_invoice', as_type=LazyI18nString)

            # Do not set to completed because that is done by the email sending task
            subject = format_map(subject, context)
            email_content = render_mail(template, context)
            mail(
                [recipient],
                subject,
                template,
                context=context,
                event=invoice.order.event,
                locale=invoice.order.locale,
                order=invoice.order,
                invoices=[invoice],
                attach_tickets=False,
                auto_email=True,
                attach_ical=False,
                plain_text_only=True,
                no_order_links=True,
            )
            invoice.order.log_action(
                'pretix.event.order.email.invoice',
                user=None,
                auth=None,
                data={
                    'subject': subject,
                    'message': email_content,
                    'position': None,
                    'recipient': recipient,
                    'invoices': [invoice.pk],
                    'attach_tickets': False,
                    'attach_ical': False,
                    'attach_other_files': [],
                    'attach_cached_files': [],
                }
            )
