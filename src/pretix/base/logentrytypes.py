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

from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.models import (
    Discount, Item, ItemCategory, Order, Question, Quota, SubEvent, TaxRule,
    Voucher, WaitingListEntry,
)

from .logentrytype_registry import (  # noqa
    ClearDataShredderMixin, LogEntryType, NoOpShredderMixin, log_entry_types,
    make_link, LogEntryTypeRegistry,
)


class EventLogEntryType(LogEntryType):
    """
    Base class for any `LogEntry` type whose `content_object` is either an `Event` itself or belongs to a specific `Event`.
    """

    def get_object_link_info(self, logentry) -> Optional[dict]:
        if hasattr(self, 'object_link_viewname'):
            content = logentry.content_object
            if not content:
                if logentry.content_type_id:
                    return {
                        'val': _('(deleted)'),
                    }
                else:
                    return

            if hasattr(self, 'content_type') and not isinstance(content, self.content_type):
                return

            return {
                'href': reverse(self.object_link_viewname, kwargs={
                    'event': logentry.event.slug,
                    'organizer': logentry.event.organizer.slug,
                    **self.object_link_args(content),
                }),
                'val': self.object_link_display_name(logentry.content_object),
            }

    def object_link_args(self, content_object):
        """Return the kwargs for the url used in a link to content_object."""
        if hasattr(self, 'object_link_argname'):
            return {self.object_link_argname: content_object.pk}
        return {}

    def object_link_display_name(self, content_object):
        """Return the display name to refer to content_object in the user interface."""
        return str(content_object)


class OrderLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Order {val}')
    object_link_viewname = 'control:event.order'
    content_type = Order

    def object_link_args(self, order):
        return {'code': order.code}

    def object_link_display_name(self, order):
        return order.code


class VoucherLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Voucher {val}…')
    object_link_viewname = 'control:event.voucher'
    object_link_argname = 'voucher'
    content_type = Voucher

    def object_link_display_name(self, voucher):
        if len(voucher.code) > 6:
            return voucher.code[:6] + "…"
        return voucher.code


class ItemLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Product {val}')
    object_link_viewname = 'control:event.item'
    object_link_argname = 'item'
    content_type = Item


class SubEventLogEntryType(EventLogEntryType):
    object_link_wrapper = pgettext_lazy('subevent', 'Date {val}')
    object_link_viewname = 'control:event.subevent'
    object_link_argname = 'subevent'
    content_type = SubEvent


class QuotaLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Quota {val}')
    object_link_viewname = 'control:event.items.quotas.show'
    object_link_argname = 'quota'
    content_type = Quota


class DiscountLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Discount {val}')
    object_link_viewname = 'control:event.items.discounts.edit'
    object_link_argname = 'discount'
    content_type = Discount


class ItemCategoryLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Category {val}')
    object_link_viewname = 'control:event.items.categories.edit'
    object_link_argname = 'category'
    content_type = ItemCategory


class QuestionLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Question {val}')
    object_link_viewname = 'control:event.items.questions.show'
    object_link_argname = 'question'
    content_type = Question


class TaxRuleLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Tax rule {val}')
    object_link_viewname = 'control:event.settings.tax.edit'
    object_link_argname = 'rule'
    content_type = TaxRule


class WaitingListEntryLogEntryType(EventLogEntryType):
    object_link_wrapper = '{val}'
    object_link_viewname = 'control:event.orders.waitinglist'
    content_type = WaitingListEntry

    def get_object_link_info(self, logentry) -> Optional[dict]:
        info = super().get_object_link_info(logentry)
        if info and 'href' in info:
            info['href'] += '?status=a&entry=' + str(logentry.content_object.pk)
        return info
