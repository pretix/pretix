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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
from collections import defaultdict

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import logentry_object_link, EventPluginRegistry, is_app_active


class VisibleOnlyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(visible=True)


def make_link(a_map, wrapper, is_active=True, event=None, plugin_name=None):
    if a_map:
        if is_active:
            a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
        elif event and plugin_name:
            a_map['val'] = '<i>{val}</i> <a href="{plugin_href}"><span data-toggle="tooltip" title="{errmes}" class="fa fa-warning fa-fw"></span></a>'.format_map({
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


class LogEntry(models.Model):
    """
    Represents a change or action that has been performed on another object
    in the database. This uses django.contrib.contenttypes to allow a
    relation to an arbitrary database object.

    :param datetime: The timestamp of the logged action
    :type datetime: datetime
    :param user: The user that performed the action
    :type user: User
    :param action_type: The type of action that has been performed. This is
       used to look up the renderer used to describe the action in a human-
       readable way. This should be some namespaced value using dotted
       notation to avoid duplicates, e.g.
       ``"pretix.plugins.banktransfer.incoming_transfer"``.
    :type action_type: str
    :param data: Arbitrary data that can be used by the log action renderer
    :type data: str
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.PROTECT)
    api_token = models.ForeignKey('TeamAPIToken', null=True, blank=True, on_delete=models.PROTECT)
    device = models.ForeignKey('Device', null=True, blank=True, on_delete=models.PROTECT)
    oauth_application = models.ForeignKey('pretixapi.OAuthApplication', null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.SET_NULL)
    organizer = models.ForeignKey('Organizer', null=True, blank=True, on_delete=models.PROTECT, db_column='organizer_link_id')
    action_type = models.CharField(max_length=255)
    data = models.TextField(default='{}')
    visible = models.BooleanField(default=True)
    shredded = models.BooleanField(default=False)

    objects = VisibleOnlyManager()
    all = models.Manager()

    class Meta:
        ordering = ('-datetime', '-id')
        indexes = [models.Index(fields=["datetime", "id"])]

    def display(self):
        log_entry_type, meta = log_entry_types.find(action_type=self.action_type)
        if log_entry_type:
            return log_entry_type.display(self)

        from ..signals import logentry_display

        for receiver, response in logentry_display.send(self.event, logentry=self):
            if response:
                return response
        return self.action_type

    @property
    def webhook_type(self):
        from pretix.api.webhooks import get_all_webhook_events

        wh_types = get_all_webhook_events()
        wh_type = None
        typepath = self.action_type
        while not wh_type and '.' in typepath:
            wh_type = wh_type or wh_types.get(typepath + ('.*' if typepath != self.action_type else ''))
            typepath = typepath.rsplit('.', 1)[0]
        return wh_type

    @property
    def notification_type(self):
        from pretix.base.notifications import get_all_notification_types

        no_type = None
        no_types = get_all_notification_types()
        typepath = self.action_type
        while not no_type and '.' in typepath:
            no_type = no_type or no_types.get(typepath + ('.*' if typepath != self.action_type else ''))
            typepath = typepath.rsplit('.', 1)[0]
        return no_type

    @cached_property
    def display_object(self):
        from . import (
            Discount, Event, Item, Order, Question, Quota,
            SubEvent, Voucher,
        )

        log_entry_type, meta = log_entry_types.find(action_type=self.action_type)
        if log_entry_type:
            link_info = log_entry_type.get_object_link_info(self)
            if is_app_active(self.event, meta['plugin']):
                return make_link(link_info, log_entry_type.object_link_wrapper)
            else:
                return make_link(link_info, log_entry_type.object_link_wrapper, is_active=False,
                                 event=self.event, plugin_name=meta['plugin'] and getattr(meta['plugin'], 'name'))

        try:
            if self.content_type.model_class() is Event:
                return ''

            co = self.content_object
        except:
            return ''

        for receiver, response in logentry_object_link.send(self.event, logentry=self):
            if response:
                return response

        if isinstance(co, (Order, Voucher, Item, SubEvent, Quota, Discount, Question)):
            logging.warning("LogEntryType missing or ill-defined: %s", self.action_type)

        return ''

    @cached_property
    def parsed_data(self):
        return json.loads(self.data)

    def delete(self, using=None, keep_parents=False):
        raise TypeError("Logs cannot be deleted.")

    @classmethod
    def bulk_postprocess(cls, objects):
        from pretix.api.webhooks import notify_webhooks

        from ..services.notifications import notify

        to_notify = [o.id for o in objects if o.notification_type]
        if to_notify:
            notify.apply_async(args=(to_notify,))
        to_wh = [o.id for o in objects if o.webhook_type]
        if to_wh:
            notify_webhooks.apply_async(args=(to_wh,))


class LogEntryTypeRegistry(EventPluginRegistry):
    def new_from_dict(self, data):
        def reg(clz):
            for action_type, plain in data.items():
                self.register(clz(action_type=action_type, plain=plain))
        return reg


log_entry_types = LogEntryTypeRegistry({'action_type': lambda o: getattr(o, 'action_type')})


class LogEntryType:
    def __init__(self, action_type=None, plain=None):
        assert self.__module__ != LogEntryType.__module__  # must not instantiate base classes, only derived ones
        if action_type: self.action_type = action_type
        if plain: self.plain = plain

    def display(self, logentry):
        if hasattr(self, 'plain'):
            plain = str(self.plain)
            if '{' in plain:
                data = defaultdict(lambda: '?', logentry.parsed_data)
                return plain.format_map(data)
            else:
                return plain

    def get_object_link_info(self, logentry) -> dict:
        pass

    def get_object_link(self, logentry):
        a_map = self.get_object_link_info(logentry)
        return make_link(a_map, self.object_link_wrapper)

    object_link_wrapper = '{val}'

    def shred_pii(self, logentry):
        raise NotImplementedError


class EventLogEntryType(LogEntryType):
    def get_object_link_info(self, logentry) -> dict:
        if hasattr(self, 'object_link_viewname') and hasattr(self, 'object_link_argname') and logentry.content_object:
            return {
                'href': reverse(self.object_link_viewname, kwargs={
                    'event': logentry.event.slug,
                    'organizer': logentry.event.organizer.slug,
                    self.object_link_argname: self.object_link_argvalue(logentry.content_object),
                }),
                'val': escape(self.object_link_display_name(logentry.content_object)),
            }

    def object_link_argvalue(self, content_object):
        return content_object.id

    def object_link_display_name(self, content_object):
        return str(content_object)


class OrderLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Order {val}')
    object_link_viewname = 'control:event.order'
    object_link_argname = 'code'

    def object_link_argvalue(self, order):
        return order.code

    def object_link_display_name(self, order):
        return order.code


class VoucherLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Voucher {val}…')
    object_link_viewname = 'control:event.voucher'
    object_link_argname = 'voucher'

    def object_link_display_name(self, order):
        return order.code[:6]


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
