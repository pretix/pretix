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

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.signals import logentry_object_link


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
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    datetime = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey('User', null=True, blank=True, on_delete=models.PROTECT)
    api_token = models.ForeignKey('TeamAPIToken', null=True, blank=True, on_delete=models.PROTECT)
    device = models.ForeignKey('Device', null=True, blank=True, on_delete=models.PROTECT)
    oauth_application = models.ForeignKey('pretixapi.OAuthApplication', null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.SET_NULL)
    action_type = models.CharField(max_length=255)
    data = models.TextField(default='{}')
    visible = models.BooleanField(default=True)
    shredded = models.BooleanField(default=False)

    objects = VisibleOnlyManager()
    all = models.Manager()

    class Meta:
        ordering = ('-datetime', '-id')

    def display(self):
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
    def organizer(self):
        from .organizer import Organizer

        if self.event:
            return self.event.organizer
        elif hasattr(self.content_object, 'event'):
            return self.content_object.event.organizer
        elif hasattr(self.content_object, 'organizer'):
            return self.content_object.organizer
        elif isinstance(self.content_object, Organizer):
            return self.content_object
        return None

    @cached_property
    def display_object(self):
        from . import (
            Discount, Event, Item, ItemCategory, Order, Question, Quota,
            SubEvent, TaxRule, Voucher,
        )

        try:
            if self.content_type.model_class() is Event:
                return ''

            co = self.content_object
        except:
            return ''
        a_map = None
        a_text = None

        if isinstance(co, Order):
            a_text = _('Order {val}')
            a_map = {
                'href': reverse('control:event.order', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'code': co.code
                }),
                'val': escape(co.code),
            }
        elif isinstance(co, Voucher):
            a_text = _('Voucher {val}…')
            a_map = {
                'href': reverse('control:event.voucher', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'voucher': co.id
                }),
                'val': escape(co.code[:6]),
            }
        elif isinstance(co, Item):
            a_text = _('Product {val}')
            a_map = {
                'href': reverse('control:event.item', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'item': co.id
                }),
                'val': escape(co.name),
            }
        elif isinstance(co, SubEvent):
            a_text = pgettext_lazy('subevent', 'Date {val}')
            a_map = {
                'href': reverse('control:event.subevent', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'subevent': co.id
                }),
                'val': escape(str(co))
            }
        elif isinstance(co, Quota):
            a_text = _('Quota {val}')
            a_map = {
                'href': reverse('control:event.items.quotas.show', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'quota': co.id
                }),
                'val': escape(co.name),
            }
        elif isinstance(co, Discount):
            a_text = _('Discount {val}')
            a_map = {
                'href': reverse('control:event.items.discounts.edit', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'discount': co.id
                }),
                'val': escape(co.internal_name),
            }
        elif isinstance(co, ItemCategory):
            a_text = _('Category {val}')
            a_map = {
                'href': reverse('control:event.items.categories.edit', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'category': co.id
                }),
                'val': escape(co.name),
            }
        elif isinstance(co, Question):
            a_text = _('Question {val}')
            a_map = {
                'href': reverse('control:event.items.questions.show', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'question': co.id
                }),
                'val': escape(co.question),
            }
        elif isinstance(co, TaxRule):
            a_text = _('Tax rule {val}')
            a_map = {
                'href': reverse('control:event.settings.tax.edit', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                    'rule': co.id
                }),
                'val': escape(co.name),
            }

        if a_text and a_map:
            a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
            return a_text.format_map(a_map)
        elif a_text:
            return a_text
        else:
            for receiver, response in logentry_object_link.send(self.event, logentry=self):
                if response:
                    return response
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
