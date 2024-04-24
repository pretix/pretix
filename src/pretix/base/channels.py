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
import logging
import warnings
from collections import OrderedDict

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.base.signals import register_sales_channel_types

logger = logging.getLogger(__name__)
_ALL_CHANNEL_TYPES = None


class SalesChannelType:
    def __repr__(self):
        return '<SalesChannelType: {}>'.format(self.identifier)

    @property
    def identifier(self) -> str:
        """
        The internal identifier of this sales channel type.
        """
        raise NotImplementedError()  # NOQA

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name of this sales channel type.
        """
        raise NotImplementedError()  # NOQA

    @property
    def icon(self) -> str:
        """
        The name of a Font Awesome icon to represent this channel type
        """
        return "circle"

    @property
    def default_created(self) -> bool:
        """
        Indication, if a sales channel of this type should automatically be created for every organizer
        """
        return True

    @property
    def multiple_allowed(self) -> bool:
        """
        Indication, if multiple sales channels of this type may exist in the same organizer
        """
        return False

    @property
    def testmode_supported(self) -> bool:
        """
        Indication, if a sales channel of this type supports test mode orders
        """
        return True

    @property
    def payment_restrictions_supported(self) -> bool:
        """
        If this property is ``True``, organizers can restrict the usage of payment providers to this sales channel type.

        Example: pretixPOS provides its own sales channel type, ignores the configured payment providers completely and
        handles payments locally. Therefore, this property should be set to ``False`` for the pretixPOS sales channel as
        the event organizer cannot restrict the usage of any payment provider through the backend.
        """
        return True

    @property
    def unlimited_items_per_order(self) -> bool:
        """
        If this property is ``True``, purchases made using sales channels of this type are not limited to the maximum
        amount of items defined in the event settings.
        """
        return False

    @property
    def customer_accounts_supported(self) -> bool:
        """
        If this property is ``True``, checkout will show the customer login step.
        """
        return True

    @property
    def discounts_supported(self) -> bool:
        """
        If this property is ``True``, this sales channel can be selected for automatic discounts.
        """
        return True


def get_all_sales_channel_types():
    from pretix.base.signals import register_sales_channel_types
    global _ALL_CHANNEL_TYPES

    if _ALL_CHANNEL_TYPES:
        return _ALL_CHANNEL_TYPES

    channels = []
    for recv, ret in register_sales_channel_types.send(None):
        if isinstance(ret, (list, tuple)):
            channels += ret
        else:
            channels.append(ret)
    channels.sort(key=lambda c: c.identifier)
    _ALL_CHANNEL_TYPES = OrderedDict([(c.identifier, c) for c in channels])
    if 'web' in _ALL_CHANNEL_TYPES:
        _ALL_CHANNEL_TYPES.move_to_end('web', last=False)
    return _ALL_CHANNEL_TYPES


def get_all_sales_channels():
    # TODO: remove me
    warnings.warn('Using get_all_sales_channels() is no longer appropriate, use get_al_sales_channel_types() instead.',
                  DeprecationWarning, stacklevel=2)
    return get_all_sales_channel_types()


class WebshopSalesChannelType(SalesChannelType):
    identifier = "web"
    verbose_name = _('Online shop')
    icon = "globe"


class ApiSalesChannelType(SalesChannelType):
    identifier = "api"
    verbose_name = _('Online shop')
    icon = "exchange"
    default_created = False
    multiple_allowed = True


SalesChannel = SalesChannelType  # TODO: remove me


@receiver(register_sales_channel_types, dispatch_uid="base_register_default_sales_channel_types")
def base_sales_channels(sender, **kwargs):
    return (
        WebshopSalesChannelType(),
    )
