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
from typing import Optional

from django.utils.translation import gettext_lazy as _
from django_countries.fields import Country

from pretix.base.models import Invoice, InvoiceAddress
from pretix.base.signals import EventPluginRegistry, Registry


class TransmissionType:
    @property
    def identifier(self) -> str:
        """
        A short and unique identifier for this transmission type.
        """
        raise NotImplementedError

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name for this transmission type to be shown internally in the backend.
        """
        raise NotImplementedError

    @property
    def public_name(self) -> str:
        """
        A human-readable name for this transmission type to be shown to the public.
        By default, this is the same as ``verbose_name``
        """
        return self.verbose_name

    @property
    def priority(self) -> int:
        """
        Returns a priority that is used for sorting transmission type. Higher priority means higher up in the list.
        Default to 100. Providers with same priority are sorted alphabetically.
        """
        return 100

    @property
    def enforce_transmission(self) -> bool:
        """
        If a transmission type enforces transmission, every invoice created with this type will be transferred.
        If not, the backend user is in some cases trusted to decide whether or not to transmit it.
        """
        return False

    def is_available(self, event, country: Country, is_business: bool) -> bool:
        providers = transmission_providers.filter(type=self.identifier, active_in=event)
        return any(
            provider.is_available(event, country, is_business)
            for provider, _ in providers
        )

    def is_exclusive(self, event, country: Country, is_business: bool) -> bool:
        """
        If a transmission type is exclusive, no other type can be chosen if this type is
        available. Use e.g. if a certain transmission type is legally required in a certain
        jurisdiction. Event can be None in organizer-level contexts. Exclusiveness has no effect if
        the type is not available.
        """
        return False

    def invoice_address_form_fields_required(self, country: Country, is_business: bool):
        return set()

    def invoice_address_form_fields_visible(self, country: Country, is_business: bool) -> set:
        return set(self.invoice_address_form_fields.keys())

    def validate_address(self, ia: InvoiceAddress):
        pass

    @property
    def invoice_address_form_fields(self) -> dict:
        """
        Return a set of form fields that **must** be prefixed with ``transmission_<identifier>_``.
        """
        return {}

    def form_data_to_transmission_info(self, form_data: dict) -> dict:
        return {
            k: form_data.get(k) for k in self.invoice_address_form_fields
        }

    def transmission_info_to_form_data(self, transmission_info: dict) -> dict:
        return transmission_info

    def describe_info(self, transmission_info: dict, country: Country, is_business: bool):
        form_data = self.transmission_info_to_form_data(transmission_info)
        data = []
        visible_field_keys = self.invoice_address_form_fields_visible(country, is_business)
        for k, f in self.invoice_address_form_fields.items():
            if k not in visible_field_keys:
                continue
            v = form_data.get(k)
            if v is True:
                v = _("Yes")
            elif v is False:
                v = _("No")
            if v:
                data.append((f.label, v))
        return data

    def pdf_watermark(self) -> Optional[str]:
        """
        Return a watermark that should be rendered across the PDF file.
        """
        return None

    def pdf_info_text(self) -> Optional[str]:
        """
        Return an info text that should be rendered on the PDF file.
        """
        return None


class TransmissionProvider:
    """
    Base class for a transmission provider. Should NOT hold internal state as the class is only
    instantiated once and then shared between events and organizers.
    """

    @property
    def identifier(self):
        """
        A short and unique identifier for this transmission provider.
        This should only contain lowercase letters and underscores.
        """
        raise NotImplementedError

    @property
    def type(self):
        """
        Identifier of the transmission type this provider provides.
        """
        raise NotImplementedError

    @property
    def verbose_name(self):
        """
        A human-readable name for this transmission provider (can be localized).
        """
        raise NotImplementedError

    @property
    def testmode_supported(self) -> bool:
        """
        Whether testmode invoices may be passed to this provider.
        """
        return False

    def is_ready(self, event) -> bool:
        """
        Return whether this provider has all required configuration to be used in this event.
        """
        raise NotImplementedError

    def is_available(self, event, country: Country, is_business: bool) -> bool:
        """
        Return whether this provider may be used for an invoice for the given recipient country and address type.
        """
        raise NotImplementedError

    def transmit(self, invoice: Invoice):
        """
        Transmit the invoice. The invoice passed as a parameter will be in status ``TRANSMISSION_STATUS_INFLIGHT``.
        Invoices that stay in this state for more than 24h will be retried automatically. Implementations are expected to:

        - Send the invoice.

        - Update the ``transmission_status`` to `TRANSMISSION_STATUS_COMPLETED` or `TRANSMISSION_STATUS_FAILED`
          after sending, as well as ``transmission_info`` with provider-specific data, and ``transmission_date`` to
          the date and time of completion.

        - Create a log entry of action type ``pretix.event.order.invoice.sent`` or
          ``pretix.event.order.invoice.sending_failed`` with the fields ``full_invoice_no``, ``transmission_provider``,
          ``transmission_type`` and a provider-specific ``data`` field.

        Make sure to either handle ``invoice.order.testmode`` properly or set ``testmode_supported`` to ``False``.
        """
        raise NotImplementedError

    @property
    def priority(self) -> int:
        """
        Returns a priority that is used for sorting transmission providers. Higher priority will be chosen over
        lower priority for transmission. Default to 100.
        """
        return 100

    def settings_url(self, event) -> Optional[str]:
        """
        Return a URL to the settings page of this provider (if any).
        """
        return None


class TransmissionProviderRegistry(EventPluginRegistry):
    def __init__(self):
        super().__init__({
            'identifier': lambda o: getattr(o, 'identifier'),
            'type': lambda o: getattr(o, 'type'),
        })

    def register(self, *objs):
        for obj in objs:
            if not isinstance(obj, TransmissionProvider):
                raise TypeError('Entries must be derived from TransmissionProvider')

            if obj.type == "email" and not obj.__module__.startswith('pretix.base.'):
                raise TypeError('No custom providers for email allowed')

        return super().register(*objs)


class TransmissionTypeRegistry(Registry):
    def __init__(self):
        super().__init__({
            'identifier': lambda o: getattr(o, 'identifier'),
        })

    def register(self, *objs):
        for obj in objs:
            if not isinstance(obj, TransmissionType):
                raise TypeError('Entries must be derived from TransmissionType')

            if not obj.__module__.startswith('pretix.base.'):
                raise TypeError('Plugins are currently not allowed to add transmission types')

        return super().register(*objs)


"""
Registry for transmission providers.

Each entry in this registry should be an instance of a subclass of ``TransmissionProvider``.
They are annotated with their ``identifier``, ``type``, and the defining ``plugin``.
"""
transmission_providers = TransmissionProviderRegistry()


"""
Registry for transmission types.

Each entry in this registry should be an instance of a subclass of ``TransmissionType``.
They are annotated with their ``identifier``.
"""
transmission_types = TransmissionTypeRegistry()


def get_transmission_types():
    return sorted(
        transmission_types.registered_entries.keys(),
        key=lambda t: (-t.priority, str(t.public_name)),
    )
