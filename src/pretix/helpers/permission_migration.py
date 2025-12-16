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
import warnings

OLD_TO_NEW_EVENT_MIGRATION = {
    "can_change_event_settings": [
        "event.settings.general:write",
        "event.settings.payment:write",
        "event.settings.plugins:write",
        "event.settings.email.sender:write",
        "event.settings.tax:write"
        "event.settings.invoicing:write",
        "event.subevents:write",
    ],
    "can_change_items": ["event.items:write"],
    "can_view_orders": ["event.orders:read"],
    "can_change_orders": ["event.orders:write", "event:cancel"],
    "can_checkin_orders": ["event.orders:checkin"],
    "can_view_vouchers": ["event.vouchers:read"],
    "can_change_vouchers": ["event.vouchers:write"],
}
OLD_TO_NEW_ORGANIZER_MIGRATION = {
    "can_create_events": ["organizer.events:create"],
    "can_change_organizer_settings": ["organizer.settings.general:write", "organizer.devices:read",
                                      "organizer.devices:write"],
    "can_change_teams": ["organizer.teams:write"],
    "can_manage_gift_cards": ["organizer.giftcards:read", "organizer.giftcards:write"],
    "can_manage_customers": ["organizer.customers:read", "organizer.customers:write"],
    "can_manage_reusable_media": ["organizer.reusablemedia:read", "organizer.reusablemedia:write"],
}
OLD_TO_NEW_EVENT_COMPAT = {
    "can_change_event_settings": ["event.settings.general:write",],
    "can_change_items": ["event.items:write"],
    "can_view_orders": ["event.orders:read"],
    "can_change_orders": ["event.orders:write"],
    "can_checkin_orders": ["event.orders:checkin"],
    "can_view_vouchers": ["event.vouchers:read"],
    "can_change_vouchers": ["event.vouchers:write"],
}
OLD_TO_NEW_ORGANIZER_COMPAT = {
    "can_create_events": ["organizer.events:create"],
    "can_change_organizer_settings": ["organizer.settings.general:write"],
    "can_change_teams": ["organizer.teams:write"],
    "can_manage_gift_cards": ["organizer.giftcards:read", "organizer.giftcards:write"],
    "can_manage_customers": ["organizer.customers:read", "organizer.customers:write"],
    "can_manage_reusable_media": ["organizer.reusablemedia:read", "organizer.reusablemedia:write"],
}


class LegacyPermissionProperty:
    name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self

        warnings.warn("Legacy permission attribute used", DeprecationWarning, stacklevel=2)

        if self.name in OLD_TO_NEW_EVENT_COMPAT:
            return instance.all_event_permissions or all(
                kk in instance.limit_event_permissions for kk in OLD_TO_NEW_EVENT_COMPAT[self.name]
            )
        if self.name in OLD_TO_NEW_ORGANIZER_COMPAT:
            return instance.all_organizer_permissions or all(
                kk in instance.limit_organizer_permissions for kk in OLD_TO_NEW_ORGANIZER_COMPAT[self.name]
            )
        raise AttributeError("Unknown legacy attribute")
