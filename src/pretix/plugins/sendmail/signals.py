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
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import copy
import datetime
import logging

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled

from pretix.base.models import SubEvent
from pretix.base.signals import (
    EventPluginSignal, event_copy_data, logentry_display, periodic_task,
)
from pretix.control.signals import nav_event
from pretix.helpers import OF_SELF
from pretix.plugins.sendmail.models import ScheduledMail
from pretix.plugins.sendmail.views import OrderSendView, WaitinglistSendView

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SubEvent)
def scheduled_mail_create(sender, **kwargs):
    subevent = kwargs.get('instance')
    event = subevent.event
    with scope(organizer=event.organizer):
        existing_rules = ScheduledMail.objects.filter(subevent=subevent).values_list('rule_id', flat=True)
        to_create = []
        for rule in event.sendmail_rules.all():
            if rule.pk not in existing_rules and subevent:
                sm = ScheduledMail(rule=rule, event=event, subevent=subevent)
                sm.recompute()
                to_create.append(sm)
        ScheduledMail.objects.bulk_create(to_create)


@receiver(nav_event, dispatch_uid="sendmail_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
        return []
    return [
        {
            'label': _('Send out emails'),
            'url': reverse('plugins:sendmail:send', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'icon': 'envelope',
            'children': [
                {
                    'label': _('Send email'),
                    'url': reverse('plugins:sendmail:send', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:sendmail' and url.url_name.startswith('send')),
                },
                {
                    'label': _('Automated emails'),
                    'url': reverse('plugins:sendmail:rule.list', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:sendmail' and url.url_name.startswith('rule.')),
                },
                {
                    'label': _('Email history'),
                    'url': reverse('plugins:sendmail:history', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:sendmail' and url.url_name == 'history'),
                },
            ]
        },
    ]


@receiver(signal=logentry_display)
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    plains = {
        'pretix.plugins.sendmail.sent': _('Mass email was sent to customers or attendees.'),
        'pretix.plugins.sendmail.sent.waitinglist': _('Mass email was sent to waiting list entries.'),
        'pretix.plugins.sendmail.order.email.sent': _('The order received a mass email.'),
        'pretix.plugins.sendmail.order.email.sent.attendee': _('A ticket holder of this order received a mass email.'),
        'pretix.plugins.sendmail.rule.added': _('An email rule was created'),
        'pretix.plugins.sendmail.rule.changed': _('An email rule was updated'),
        'pretix.plugins.sendmail.rule.order.email.sent': _('A scheduled email was sent to the order'),
        'pretix.plugins.sendmail.rule.order.position.email.sent': _('A scheduled email was sent to a ticket holder'),
        'pretix.plugins.sendmail.rule.deleted': _('An email rule was deleted'),
    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(periodic_task)
def sendmail_run_rules(sender, **kwargs):
    with scopes_disabled():
        mails = ScheduledMail.objects.all()

        unchanged = []
        for m in mails.filter(Q(last_computed__isnull=True)
                              | Q(subevent__last_modified__gt=F('last_computed'))
                              | Q(event__last_modified__gt=F('last_computed'))):
            previous = m.computed_datetime
            m.recompute()
            if m.computed_datetime != previous:
                m.save(update_fields=['last_computed', 'computed_datetime', 'state'])
            else:
                unchanged.append(m.pk)

        if unchanged:
            # Theoretically, we don't need to write back the unchanged ones to the database… but that will cause us to
            # recompute them on every run until eternity. So we want to set their last_computed date to something more
            # recent... but not for all of them at once, in case it's millions, so we don't stress the database without
            # cause
            batch_size = max(connection.ops.bulk_batch_size(['id'], unchanged) - 2, 100)
            for i in range(max(1, 5000 // batch_size)):
                ScheduledMail.objects.filter(pk__in=unchanged[i * batch_size:batch_size]).update(last_computed=now())

        mails.filter(
            state=ScheduledMail.STATE_SCHEDULED,
            computed_datetime__lte=timezone.now() - datetime.timedelta(days=2),
            event__live=True,
        ).update(
            state=ScheduledMail.STATE_MISSED
        )
        for m_id in mails.filter(
            state__in=(ScheduledMail.STATE_SCHEDULED, ScheduledMail.STATE_FAILED),
            rule__enabled=True,
            event__live=True,
            computed_datetime__gte=timezone.now() - datetime.timedelta(days=2),
            computed_datetime__lte=timezone.now(),
        ).values_list('pk', flat=True):
            # We try to send the emails in a "reasonably safe" way.
            # - We use PostgreSQL-level locking to prevent to cronjob processes trying to
            #   work on the same email at the same time if .send() takes a long time.
            # - If we fail in between emails due to some kind of pretix-level bug, such as
            #   an exception during placeholder rendering, we store a ``last_successful_order_id``
            #   pointer and continue from there in our retry attempt, avoiding to send all the
            #   previous emails a second time.
            # - If we fail due to a system-level failure such as a signal interrupt or a lost
            #   connection to the database, this won't help us recover and on the next run, all
            #   emails might be sent a second time. This isn't nice, but any solution would either
            #   require settings some arbitrary timeout for a process or risk not sending some
            #   emails at all. Under the assumption that system-level failures are rare and (more
            #   importantly) usually don't happen multiple times in a row, this seems like a
            #   good tradeoff.
            # - We never retry for more than two days.

            with transaction.atomic(durable=True):
                m = ScheduledMail.objects.select_for_update(
                    of=OF_SELF,
                    skip_locked=connection.features.has_select_for_update_skip_locked
                ).filter(pk=m_id).first()
                if not m or m.state not in (ScheduledMail.STATE_SCHEDULED, ScheduledMail.STATE_FAILED):
                    # object is currently locked by other thread (currently being sent)
                    # or has been sent in the meantime
                    continue

                try:
                    m.send()
                    m.state = ScheduledMail.STATE_COMPLETED
                    m.save(update_fields=['state', 'last_successful_order_id'])
                except Exception as e:
                    logger.exception('Could not send emails, will retry')
                    m.state = ScheduledMail.STATE_FAILED
                    m.save(update_fields=['state', 'last_successful_order_id'])

                    if settings.SENTRY_ENABLED:
                        from sentry_sdk import capture_exception
                        capture_exception(e)


@receiver(signal=event_copy_data, dispatch_uid="sendmail_copy_event")
def sendmail_copy_data_receiver(sender, other, item_map, **kwargs):
    if sender.sendmail_rules.exists():  # idempotency
        return

    for r in other.sendmail_rules.prefetch_related('limit_products'):
        limit_products = list(r.limit_products.all())
        r = copy.copy(r)
        r.pk = None
        r.event = sender
        r.save()
        if limit_products:
            r.limit_products.add(*[item_map[p.id] for p in limit_products if p.id in item_map])


sendmail_view_classes = EventPluginSignal()
"""
This signal allows you to register subclasses of ``pretix.plugins.sendmail.views.BaseSenderView`` that should be
discovered by this plugin.

As with all plugin signals, the ``sender`` keyword will contain the event.
"""


@receiver(signal=sendmail_view_classes, dispatch_uid="sendmail_register_sendmail_view_classes")
def register_view_classes(sender, **kwargs):
    return [OrderSendView, WaitinglistSendView]
