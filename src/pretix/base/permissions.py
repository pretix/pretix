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

import logging
from collections import OrderedDict, namedtuple

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import (
    register_event_permissions, register_organizer_permissions,
)

logger = logging.getLogger(__name__)
_ALL_EVENT_PERMISSIONS = None
_ALL_ORGANIZER_PERMISSIONS = None


Permission = namedtuple('Permission', ('name', 'label', 'plugin_name', 'help_text'))


def get_all_event_permissions():
    global _ALL_EVENT_PERMISSIONS

    if _ALL_EVENT_PERMISSIONS:
        return _ALL_EVENT_PERMISSIONS

    types = OrderedDict()
    for recv, ret in register_event_permissions.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.name] = r
        else:
            types[ret.name] = ret
    _ALL_EVENT_PERMISSIONS = types
    return types


def get_all_organizer_permissions():
    global _ALL_ORGANIZER_PERMISSIONS

    if _ALL_ORGANIZER_PERMISSIONS:
        return _ALL_ORGANIZER_PERMISSIONS

    types = OrderedDict()
    for recv, ret in register_organizer_permissions.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.name] = r
        else:
            types[ret.name] = ret
    _ALL_ORGANIZER_PERMISSIONS = types
    return types


@receiver(register_event_permissions, dispatch_uid="base_register_default_event_permissions")
def register_default_event_permissions(sender, **kwargs):
    return [
        Permission("event.settings.general:write", _("Change general settings"), None, None),
        Permission("event.settings.payment:write", _("Change payment settings"), None, None),
        Permission("event.settings.plugins:write", _("Change plugin settings"), None, None),
        Permission("event.settings.email.sender:write", _("Change email sending settings"), None, None),
        Permission("event.settings.tax:write", _("Change tax rules"), None, None),
        Permission("event.settings.invoicing:write", _("Change invoicing settings"), None, None),
        Permission("event.subevents:write", pgettext_lazy("subevent", "Change event series dates"), None, None),
        Permission("event.items:write", _("Change products and quotas"), None, None),  # and questions but that might change?
        Permission("event.orders:read", _("View orders"), None, None),
        Permission("event.orders:write", _("Change orders"), None, _("This includes the ability to cancel and refund individual orders.")),
        Permission("event.orders:checkin", _("Check-in orders"), None, None),
        Permission("event:cancel", pgettext_lazy("subevent", "Cancel the entire event or date"), None, None),
        Permission("event.vouchers:read", _("View vouchers"), None, None),
        Permission("event.vouchers:write", _("Change vouchers"), None, None),
    ]


@receiver(register_organizer_permissions, dispatch_uid="base_register_default_organizer_permissions")
def register_default_organizer_permissions(sender, **kwargs):
    return [
        Permission("organizer.events:create", _("Create events"), None, None),
        Permission("organizer.settings.general:write", _("Change settings"), None, None),
        Permission("organizer.teams:write", _("Change teams"), None,
                   _("This includes the ability to give someone (including oneself) additional permissions.")),
        Permission("organizer.giftcards:read", _("View gift cards"), None, None),
        Permission("organizer.giftcards:write", _("Change gift cards"), None, None),
        Permission("organizer.customers:read", _("View customer accounts"), None, None),
        Permission("organizer.customers:write", _("Change customer accounts"), None, None),
        Permission("organizer.reusablemedia:read", _("View reusable media"), None, None),
        Permission("organizer.reusablemedia:write", _("Change reusable media"), None, None),
        Permission("organizer.devices:read", _("View devices"), None, None),
        Permission("organizer.devices:write", _("Change devices"), None,
                   _("This inclues the ability to give access to events and date oneself does not have access to.")),
    ]
