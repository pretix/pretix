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

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import connections, models
from django.utils.functional import cached_property

from pretix.helpers.celery import get_task_priority


class VisibleOnlyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(visible=True)


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
    object_id = models.PositiveBigIntegerField(db_index=True)
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
        from pretix.base.logentrytype_registry import log_entry_types

        log_entry_type, meta = log_entry_types.get(action_type=self.action_type)
        if log_entry_type:
            return log_entry_type.display(self, self.parsed_data)

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
        from pretix.base.logentrytype_registry import (
            log_entry_types, make_link,
        )
        from pretix.base.signals import is_app_active, logentry_object_link

        from . import (
            Discount, Event, Item, Order, Question, Quota, SubEvent, Voucher,
        )

        log_entry_type, meta = log_entry_types.get(action_type=self.action_type)
        if log_entry_type:
            sender = self.event if self.event else self.organizer
            link_info = log_entry_type.get_object_link_info(self)
            if is_app_active(sender, meta['plugin']):
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
    def bulk_create_and_postprocess(cls, objects):
        if connections['default'].features.can_return_rows_from_bulk_insert:
            cls.objects.bulk_create(objects)
        else:
            for le in objects:
                le.save()
        cls.bulk_postprocess(objects)

    @classmethod
    def bulk_postprocess(cls, objects):
        from pretix.api.webhooks import notify_webhooks

        from ..services.notifications import notify

        to_notify = [o.id for o in objects if o.notification_type]
        if to_notify:
            organizer_ids = set(o.organizer_id for o in objects if o.notification_type)
            notify.apply_async(
                args=(to_notify,),
                priority=settings.PRIORITY_CELERY_HIGHEST_FUNC(
                    get_task_priority("notifications", oid) for oid in organizer_ids
                ),
            )
        to_wh = [o.id for o in objects if o.webhook_type]
        if to_wh:
            organizer_ids = set(o.organizer_id for o in objects if o.webhook_type)
            notify_webhooks.apply_async(
                args=(to_wh,),
                priority=settings.PRIORITY_CELERY_HIGHEST_FUNC(
                    get_task_priority("notifications", oid) for oid in organizer_ids
                ),
            )
