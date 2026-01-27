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
from collections import OrderedDict
from typing import Dict, List, NamedTuple, Tuple

from django.dispatch import receiver
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import (
    register_event_permission_groups, register_organizer_permission_groups,
)

logger = logging.getLogger(__name__)
_ALL_EVENT_PERMISSIONS = None
_ALL_ORGANIZER_PERMISSIONS = None


class PermissionOption(NamedTuple):
    actions: Tuple[str, ...]
    label: str | Promise
    help_text: str | Promise = None


class PermissionGroup(NamedTuple):
    name: str
    label: str | Promise
    actions: List[str]
    options: List[PermissionOption]
    help_text: str | Promise = None


def get_all_event_permission_groups() -> Dict[str, PermissionGroup]:
    global _ALL_EVENT_PERMISSIONS

    if _ALL_EVENT_PERMISSIONS:
        return _ALL_EVENT_PERMISSIONS

    types = OrderedDict()
    for recv, ret in register_event_permission_groups.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.name] = r
        else:
            types[ret.name] = ret
    _ALL_EVENT_PERMISSIONS = types
    return types


def get_all_organizer_permission_groups() -> Dict[str, PermissionGroup]:
    global _ALL_ORGANIZER_PERMISSIONS

    if _ALL_ORGANIZER_PERMISSIONS:
        return _ALL_ORGANIZER_PERMISSIONS

    types = OrderedDict()
    for recv, ret in register_organizer_permission_groups.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.name] = r
        else:
            types[ret.name] = ret
    _ALL_ORGANIZER_PERMISSIONS = types
    return types


OPTS_ALL_READ = [
    PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "View")),
    PermissionOption(actions=("write",), label=pgettext_lazy("permission_level", "View and change")),
]
OPTS_ALL_READ_SETTINGS_API = [
    PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "View"),
                     help_text=_("API only")),
    PermissionOption(actions=("write",), label=pgettext_lazy("permission_level", "View and change")),
]
OPTS_ALL_READ_SETTINGS_PARENT = [
    PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "View"),
                     help_text=_("Menu item will only show up if the user has permission for general settings.")),
    PermissionOption(actions=("write",), label=pgettext_lazy("permission_level", "View and change")),
]
OPTS_READ_WRITE = [
    PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "No access")),
    PermissionOption(actions=("read",), label=pgettext_lazy("permission_level", "View")),
    PermissionOption(actions=("read", "write"), label=pgettext_lazy("permission_level", "View and change")),
]


@receiver(register_event_permission_groups, dispatch_uid="base_register_default_event_permissions")
def register_default_event_permissions(sender, **kwargs):
    return [
        PermissionGroup(
            name="event.settings.general",
            label=_("General settings"),
            actions=["write"],
            options=OPTS_ALL_READ_SETTINGS_API,
            help_text=_(
                "This includes access to all settings not listed explicitly below, including plugin settings."
            ),
        ),
        PermissionGroup(
            name="event.settings.payment",
            label=_("Payment settings"),
            actions=["write"],
            options=OPTS_ALL_READ_SETTINGS_PARENT,
        ),
        PermissionGroup(
            name="event.settings.tax",
            label=_("Tax settings"),
            actions=["write"],
            options=OPTS_ALL_READ_SETTINGS_PARENT,
        ),
        PermissionGroup(
            name="event.settings.invoicing",
            label=_("Invoicing settings"),
            actions=["write"],
            options=OPTS_ALL_READ_SETTINGS_PARENT,
        ),
        PermissionGroup(
            name="event.subevents",
            label=_("Event series dates"),
            actions=["write"],
            options=OPTS_ALL_READ,
        ),
        PermissionGroup(
            name="event.items",
            label=_("Products, quotas and questions"),
            actions=["write"],
            options=OPTS_ALL_READ,
            help_text=_("Also includes related objects like categories or discounts."),
        ),
        PermissionGroup(
            name="event.orders",
            label=_("Orders"),
            actions=["read", "write", "checkin"],
            options=[
                PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "No access")),
                PermissionOption(actions=("checkin",), label=pgettext_lazy("permission_level", "Only check-in")),
                PermissionOption(actions=("read",), label=pgettext_lazy("permission_level", "View all")),
                PermissionOption(actions=("read", "checkin"), label=pgettext_lazy("permission_level", "View all and check-in")),
                PermissionOption(actions=("read", "write"), label=pgettext_lazy("permission_level", "View all and change"),
                                 help_text=_("Includes the ability to cancel and refund individual orders.")),
            ],
            help_text=_("Also includes related objects like the waiting list."),
        ),
        PermissionGroup(
            name="event.vouchers",
            label=_("Vouchers"),
            actions=["read", "write"],
            options=OPTS_READ_WRITE,
        ),
        PermissionGroup(
            name="event",
            label=_("Full event or date cancellation"),
            actions=["cancel"],
            options=[
                # If we ever add more actions, we need a new UI idea here
                PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "Not allowed")),
                PermissionOption(actions=("cancel",), label=pgettext_lazy("permission_level", "Allowed")),
            ],
            help_text="",
        ),
    ]


@receiver(register_organizer_permission_groups, dispatch_uid="base_register_default_organizer_permissions")
def register_default_organizer_permissions(sender, **kwargs):
    return [
        PermissionGroup(
            name="organizer.events",
            label=_("Events"),
            actions=["create"],
            options=[
                PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "Only existing events")),
                PermissionOption(actions=("create",), label=pgettext_lazy("permission_level", "Create new events")),
            ],
            help_text="",
        ),
        PermissionGroup(
            name="organizer.settings.general",
            label=_("Settings"),
            actions=["write"],
            options=OPTS_ALL_READ_SETTINGS_API,
            help_text=_("This includes access to all organizer-level functionality not listed explicitly below, including plugin settings."),
        ),
        PermissionGroup(
            name="organizer.teams",
            label=_("Teams"),
            actions=["write"],
            options=[
                PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "No access")),
                PermissionOption(actions=("write",), label=pgettext_lazy("permission_level", "View and change"),
                                 help_text=_("Includes the ability to give someone (including oneself) additional permissions.")),
            ],
        ),
        PermissionGroup(
            name="organizer.giftcards",
            label=_("Gift cards"),
            actions=["read", "write"],
            options=OPTS_READ_WRITE,
        ),
        PermissionGroup(
            name="organizer.customers",
            label=_("Customers"),
            actions=["read", "write"],
            options=OPTS_READ_WRITE,
        ),
        PermissionGroup(
            name="organizer.reusablemedia",
            label=_("Reusable media"),
            actions=["read", "write"],
            options=OPTS_READ_WRITE,
        ),
        PermissionGroup(
            name="organizer.devices",
            label=_("Devices"),
            actions=["read", "write"],
            options=[
                PermissionOption(actions=tuple(), label=pgettext_lazy("permission_level", "No access")),
                PermissionOption(actions=("read",), label=pgettext_lazy("permission_level", "View")),
                PermissionOption(actions=("read", "write"), label=pgettext_lazy("permission_level", "View and change"),
                                 help_text=_("Includes the ability to give access to events and data oneself does not have access to.")),
            ],
        ),
        PermissionGroup(
            name="organizer.seatingplans",
            label=_("Seating plans"),
            actions=["write"],
            options=OPTS_ALL_READ,
        ),
    ]
