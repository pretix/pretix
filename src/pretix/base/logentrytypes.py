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
from collections import defaultdict

from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import EventPluginRegistry


def make_link(a_map, wrapper, is_active=True, event=None, plugin_name=None):
    if a_map:
        if is_active:
            a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
        elif event and plugin_name:
            a_map['val'] = (
                '<i>{val}</i> <a href="{plugin_href}">'
                '<span data-toggle="tooltip" title="{errmes}" class="fa fa-warning fa-fw"></span></a>'
            ).format_map({
                **a_map,
                "errmes": _("The relevant plugin is currently not active. To activate it, click here to go to the plugin settings."),
                "plugin_href": reverse('control:event.settings.plugins', kwargs={
                    'organizer': event.organizer.slug,
                    'event': event.slug,
                }) + '#plugin_' + plugin_name,
            })
        else:
            a_map['val'] = '<i>{val}</i> <span data-toggle="tooltip" title="{errmes}" class="fa fa-warning fa-fw"></span>'.format_map({
                **a_map,
                "errmes": _("The relevant plugin is currently not active."),
            })
        return wrapper.format_map(a_map)


class LogEntryTypeRegistry(EventPluginRegistry):
    def __init__(self):
        super().__init__({'action_type': lambda o: getattr(o, 'action_type')})

    def register(self, *objs):
        for obj in objs:
            if not isinstance(obj, LogEntryType):
                raise TypeError('Entries must be derived from LogEntryType')

            if obj.__module__ == LogEntryType.__module__:
                raise TypeError('Must not register base classes, only derived ones')

        return super().register(*objs)

    def new_from_dict(self, data):
        """
        Register multiple instance of a `LogEntryType` class with different `action_type`
        and plain text strings, as given by the items of the specified data dictionary.

        This method is designed to be used as a decorator as follows:

        .. code-block:: python

            @log_entry_types.new_from_dict({
                'pretix.event.item.added': _('The product has been created.'),
                'pretix.event.item.changed': _('The product has been changed.'),
                # ...
            })
            class CoreItemLogEntryType(ItemLogEntryType):
                # ...

        :param data: action types and descriptions
                     ``{"some_action_type": "Plain text description", ...}``
        """
        def reg(clz):
            for action_type, plain in data.items():
                self.register(clz(action_type=action_type, plain=plain))
            return clz
        return reg


"""
Registry for LogEntry types.

Each entry in this registry should be an instance of a subclass of ``LogEntryType``.
They are annotated with their ``action_type`` and the defining ``plugin``.
"""
log_entry_types = LogEntryTypeRegistry()


class LogEntryType:
    """
    Base class for a type of LogEntry, identified by its action_type.
    """

    def __init__(self, action_type=None, plain=None):
        if action_type:
            self.action_type = action_type
        if plain:
            self.plain = plain

    def display(self, logentry):
        """
        Returns the message to be displayed for a given logentry of this type.

        :return: `str` or `LazyI18nString`
        """
        if hasattr(self, 'plain'):
            plain = str(self.plain)
            if '{' in plain:
                data = defaultdict(lambda: '?', logentry.parsed_data)
                return plain.format_map(data)
            else:
                return plain

    def get_object_link_info(self, logentry) -> dict:
        """
        Return information to generate a link to the `content_object` of a given log entry.

        Not implemented in the base class, causing the object link to be omitted.

        :return: Dictionary with the keys ``href`` (containing a URL to view/edit the object) and ``val`` (containing the
                 escaped text for the anchor element)
        """
        pass

    def get_object_link(self, logentry):
        a_map = self.get_object_link_info(logentry)
        return make_link(a_map, self.object_link_wrapper)

    object_link_wrapper = '{val}'

    def shred_pii(self, logentry):
        """
        To be used for shredding personally identified information contained in the data field of a LogEntry of this
        type.
        """
        raise NotImplementedError


class EventLogEntryType(LogEntryType):
    """
    Base class for any `LogEntry` type whose `content_object` is either an `Event` itself or belongs to a specific `Event`.
    """

    def get_object_link_info(self, logentry) -> dict:
        if hasattr(self, 'object_link_viewname') and logentry.content_object:
            return {
                'href': reverse(self.object_link_viewname, kwargs={
                    'event': logentry.event.slug,
                    'organizer': logentry.event.organizer.slug,
                    **self.object_link_args(logentry.content_object),
                }),
                'val': escape(self.object_link_display_name(logentry.content_object)),
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

    def object_link_args(self, order):
        return {'code': order.code}

    def object_link_display_name(self, order):
        return order.code


class VoucherLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Voucher {val}…')
    object_link_viewname = 'control:event.voucher'
    object_link_argname = 'voucher'

    def object_link_display_name(self, voucher):
        if len(voucher.code) > 6:
            return voucher.code[:6] + "…"
        return voucher.code


class ItemLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Product {val}')
    object_link_viewname = 'control:event.item'
    object_link_argname = 'item'


class SubEventLogEntryType(EventLogEntryType):
    object_link_wrapper = pgettext_lazy('subevent', 'Date {val}')
    object_link_viewname = 'control:event.subevent'
    object_link_argname = 'subevent'


class QuotaLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Quota {val}')
    object_link_viewname = 'control:event.items.quotas.show'
    object_link_argname = 'quota'


class DiscountLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Discount {val}')
    object_link_viewname = 'control:event.items.discounts.edit'
    object_link_argname = 'discount'


class ItemCategoryLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Category {val}')
    object_link_viewname = 'control:event.items.categories.edit'
    object_link_argname = 'category'


class QuestionLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Question {val}')
    object_link_viewname = 'control:event.items.questions.show'
    object_link_argname = 'question'


class TaxRuleLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Tax rule {val}')
    object_link_viewname = 'control:event.settings.tax.edit'
    object_link_argname = 'rule'


class NoOpShredderMixin:
    def shred_pii(self, logentry):
        pass


class ClearDataShredderMixin:
    def shred_pii(self, logentry):
        logentry.data = None
