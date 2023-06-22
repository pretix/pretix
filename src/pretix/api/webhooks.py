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
import json
import logging
import time
from collections import OrderedDict
from datetime import timedelta

import requests
from django.db import DatabaseError, connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import scope, scopes_disabled
from requests import RequestException

from pretix.api.models import (
    WebHook, WebHookCall, WebHookCallRetry, WebHookEventListener,
)
from pretix.api.signals import register_webhook_events
from pretix.base.models import LogEntry
from pretix.base.services.tasks import ProfiledTask, TransactionAwareTask
from pretix.base.signals import periodic_task
from pretix.celery_app import app
from pretix.helpers import OF_SELF

logger = logging.getLogger(__name__)
_ALL_EVENTS = None


class WebhookEvent:
    def __init__(self):
        pass

    def __repr__(self):
        return '<WebhookEvent: {}>'.format(self.action_type)

    @property
    def action_type(self) -> str:
        """
        The action_type string that this notification handles, for example
        ``"pretix.event.order.paid"``. Only one notification type should be registered
        per action type.
        """
        raise NotImplementedError()  # NOQA

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name of this notification type.
        """
        raise NotImplementedError()  # NOQA

    def build_payload(self, logentry: LogEntry) -> dict:
        """
        This is the main function that you should override. It is supposed to turn a log entry
        object into a dictionary that can be used as the webhook payload.
        """
        raise NotImplementedError()  # NOQA


def get_all_webhook_events():
    global _ALL_EVENTS

    if _ALL_EVENTS:
        return _ALL_EVENTS

    types = OrderedDict()
    for recv, ret in register_webhook_events.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.action_type] = r
        else:
            types[ret.action_type] = ret
    _ALL_EVENTS = types
    return types


class ParametrizedWebhookEvent(WebhookEvent):
    def __init__(self, action_type, verbose_name):
        self._action_type = action_type
        self._verbose_name = verbose_name
        super().__init__()

    @property
    def action_type(self):
        return self._action_type

    @property
    def verbose_name(self):
        return self._verbose_name


class ParametrizedOrderWebhookEvent(ParametrizedWebhookEvent):
    def build_payload(self, logentry: LogEntry):
        order = logentry.content_object
        if not order:
            return None

        return {
            'notification_id': logentry.pk,
            'organizer': order.event.organizer.slug,
            'event': order.event.slug,
            'code': order.code,
            'action': logentry.action_type,
        }


class ParametrizedEventWebhookEvent(ParametrizedWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        if logentry.action_type == 'pretix.event.deleted':
            organizer = logentry.content_object
            return {
                'notification_id': logentry.pk,
                'organizer': organizer.slug,
                'event': logentry.parsed_data.get('slug'),
                'action': logentry.action_type,
            }

        event = logentry.content_object
        if not event:
            return None

        return {
            'notification_id': logentry.pk,
            'organizer': event.organizer.slug,
            'event': event.slug,
            'action': logentry.action_type,
        }


class ParametrizedSubEventWebhookEvent(ParametrizedWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        # do not use content_object, this is also called in deletion
        return {
            'notification_id': logentry.pk,
            'organizer': logentry.event.organizer.slug,
            'event': logentry.event.slug,
            'subevent': logentry.object_id,
            'action': logentry.action_type,
        }


class ParametrizedItemWebhookEvent(ParametrizedWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        # do not use content_object, this is also called in deletion
        return {
            'notification_id': logentry.pk,
            'organizer': logentry.event.organizer.slug,
            'event': logentry.event.slug,
            'item': logentry.object_id,
            'action': logentry.action_type,
        }


class ParametrizedOrderPositionWebhookEvent(ParametrizedOrderWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        d = super().build_payload(logentry)
        if d is None:
            return None
        d['orderposition_id'] = logentry.parsed_data.get('position')
        d['orderposition_positionid'] = logentry.parsed_data.get('positionid')
        d['checkin_list'] = logentry.parsed_data.get('list')
        d['first_checkin'] = logentry.parsed_data.get('first_checkin')
        return d


class ParametrizedWaitingListEntryWebhookEvent(ParametrizedWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        # do not use content_object, this is also called in deletion
        return {
            'notification_id': logentry.pk,
            'organizer': logentry.event.organizer.slug,
            'event': logentry.event.slug,
            'waitinglistentry': logentry.object_id,
            'action': logentry.action_type,
        }


@receiver(register_webhook_events, dispatch_uid="base_register_default_webhook_events")
def register_default_webhook_events(sender, **kwargs):
    return (
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.placed',
            _('New order placed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.placed.require_approval',
            _('New order requires approval'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.paid',
            _('Order marked as paid'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.canceled',
            _('Order canceled'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.reactivated',
            _('Order reactivated'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.expired',
            _('Order expired'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.expirychanged',
            _('Order expiry date changed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.modified',
            _('Order information changed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.contact.changed',
            _('Order contact address changed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.changed.*',
            _('Order changed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.created',
            _('Refund of payment created'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.created.externally',
            _('External refund of payment'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.requested',
            _('Refund of payment requested by customer'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.done',
            _('Refund of payment completed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.canceled',
            _('Refund of payment canceled'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.refund.failed',
            _('Refund of payment failed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.payment.confirmed',
            _('Payment confirmed'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.approved',
            _('Order approved'),
        ),
        ParametrizedOrderWebhookEvent(
            'pretix.event.order.denied',
            _('Order denied'),
        ),
        ParametrizedOrderPositionWebhookEvent(
            'pretix.event.checkin',
            _('Ticket checked in'),
        ),
        ParametrizedOrderPositionWebhookEvent(
            'pretix.event.checkin.reverted',
            _('Ticket check-in reverted'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.added',
            _('Event created'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.changed',
            _('Event details changed'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.deleted',
            _('Event deleted'),
        ),
        ParametrizedSubEventWebhookEvent(
            'pretix.subevent.added',
            pgettext_lazy('subevent', 'Event series date added'),
        ),
        ParametrizedSubEventWebhookEvent(
            'pretix.subevent.changed',
            pgettext_lazy('subevent', 'Event series date changed'),
        ),
        ParametrizedSubEventWebhookEvent(
            'pretix.subevent.deleted',
            pgettext_lazy('subevent', 'Event series date deleted'),
        ),
        ParametrizedItemWebhookEvent(
            'pretix.event.item.*',
            _('Product changed (including product added or deleted and including changes to nested objects like '
              'variations or bundles)'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.live.activated',
            _('Shop taken live'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.live.deactivated',
            _('Shop taken offline'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.testmode.activated',
            _('Test-Mode of shop has been activated'),
        ),
        ParametrizedEventWebhookEvent(
            'pretix.event.testmode.deactivated',
            _('Test-Mode of shop has been deactivated'),
        ),
        ParametrizedWaitingListEntryWebhookEvent(
            'pretix.event.orders.waitinglist.added',
            _('Waiting list entry added'),
        ),
        ParametrizedWaitingListEntryWebhookEvent(
            'pretix.event.orders.waitinglist.changed',
            _('Waiting list entry changed'),
        ),
        ParametrizedWaitingListEntryWebhookEvent(
            'pretix.event.orders.waitinglist.deleted',
            _('Waiting list entry deleted'),
        ),
        ParametrizedWaitingListEntryWebhookEvent(
            'pretix.event.orders.waitinglist.voucher_assigned',
            _('Waiting list entry received voucher'),
        ),
    )


@app.task(base=TransactionAwareTask, max_retries=9, default_retry_delay=900, acks_late=True)
def notify_webhooks(logentry_ids: list):
    if not isinstance(logentry_ids, list):
        logentry_ids = [logentry_ids]
    qs = LogEntry.all.select_related('event', 'event__organizer').filter(id__in=logentry_ids)
    _org, _at, webhooks = None, None, None
    for logentry in qs:
        if not logentry.organizer:
            break  # We need to know the organizer

        notification_type = logentry.webhook_type

        if not notification_type:
            break  # Ignore, no webhooks for this event type

        if _org != logentry.organizer or _at != logentry.action_type or webhooks is None:
            _org = logentry.organizer
            _at = logentry.action_type

            # All webhooks that registered for this notification
            event_listener = WebHookEventListener.objects.filter(
                webhook=OuterRef('pk'),
                action_type=notification_type.action_type
            )
            webhooks = WebHook.objects.annotate(has_el=Exists(event_listener)).filter(
                organizer=logentry.organizer,
                has_el=True,
                enabled=True
            )
            if logentry.event_id:
                webhooks = webhooks.filter(
                    Q(all_events=True) | Q(limit_events__pk=logentry.event_id)
                )

        for wh in webhooks:
            send_webhook.apply_async(args=(logentry.id, notification_type.action_type, wh.pk))


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=60, acks_late=True, autoretry_for=(DatabaseError,),)
def send_webhook(self, logentry_id: int, action_type: str, webhook_id: int, retry_count: int = 0):
    """
    Sends out a specific webhook using adequate retry and error handling logic.

    Our retry logic is a little complex since we have different constraints here:

    1. We historically documented that we retry for up to three days, so we want to keep that
       promise. We want to use (approximately) exponentially increasing times to keep load
       manageable.

    2. We want to use Celery's ``acks_late=True`` options which prevents lost tasks if a worker
       crashes.

    3. A limitation of Celery's redis broker implementation is that it can not properly handle
       tasks that *run or wait* longer than `visibility_timeout`, which defaults to 1h, when
       ``acks_late`` is enabled. So any task with a *retry interval* of >1h will be restarted
       many times because celery believes the worker has crashed.

    4. We do like that the first few retries happen within a few seconds to work around very
       intermittent connectivity issues quickly. For the longer retries with multiple hours,
       we don't care if they are emitted a few minutes too late.

    We therefore have a two-phase retry process:

    - For all retry intervals below 5 minutes, which is the first 3 retries currently, we
      schedule a new celery task directly with an increased retry_count. We do *not* use
      celery's retry() call currently to make the retry process in both phases more similar,
      there should not be much of a difference though (except that the initial task will be in
      SUCCESS state, but we don't check that status anywhere).

    - For all retry intervals of at least 5 minutes, we create a database entry. Then, the
      periodic task ``schedule_webhook_retries_on_celery`` will schedule celery tasks for them
      once their time has come.
    """
    retry_intervals = (
        5,  # + 5 seconds
        30,  # + 30 seconds
        60,  # + 1 minute
        300,  # + 5 minutes
        1200,  # + 20 minutes
        3600,  # + 60 minutes
        1440,  # + 4 hours
        21600,  # + 6 hours
        43200,  # + 12 hours
        43200,  # + 24 hours
        86400,  # + 24 hours
    )  # added up, these are approximately 3 days, as documented
    retry_celery_cutoff = 300

    with scopes_disabled():
        webhook = WebHook.objects.get(id=webhook_id)

    with scope(organizer=webhook.organizer), transaction.atomic():
        logentry = LogEntry.all.get(id=logentry_id)
        types = get_all_webhook_events()
        event_type = types.get(action_type)
        if not event_type or not webhook.enabled:
            return 'obsolete-webhook'  # Ignore, e.g. plugin not installed

        payload = event_type.build_payload(logentry)
        if payload is None:
            # Content object deleted?
            return 'obsolete-payload'

        t = time.time()

        try:
            resp = requests.post(
                webhook.target_url,
                json=payload,
                allow_redirects=False,
                timeout=30,
            )
            WebHookCall.objects.create(
                webhook=webhook,
                action_type=logentry.action_type,
                target_url=webhook.target_url,
                is_retry=self.request.retries > 0,
                execution_time=time.time() - t,
                return_code=resp.status_code,
                payload=json.dumps(payload),
                response_body=resp.text[:1024 * 1024],
                success=200 <= resp.status_code <= 299
            )
            if resp.status_code == 410:
                webhook.enabled = False
                webhook.save()
                return 'gone'
            elif resp.status_code > 299:
                if retry_count >= len(retry_intervals):
                    return 'retry-given-up'
                elif retry_intervals[retry_count] < retry_celery_cutoff:
                    send_webhook.apply_async(args=(logentry_id, action_type, webhook_id, retry_count + 1),
                                             countdown=retry_intervals[retry_count])
                    return 'retry-via-celery'
                else:
                    webhook.retries.update_or_create(
                        logentry=logentry,
                        defaults=dict(
                            retry_not_before=now() + timedelta(seconds=retry_intervals[retry_count]),
                            retry_count=retry_count + 1,
                            action_type=action_type,
                        ),
                    )
                    return 'retry-via-db'
            return 'ok'
        except RequestException as e:
            WebHookCall.objects.create(
                webhook=webhook,
                action_type=logentry.action_type,
                target_url=webhook.target_url,
                is_retry=self.request.retries > 0,
                execution_time=time.time() - t,
                return_code=0,
                payload=json.dumps(payload),
                response_body=str(e)[:1024 * 1024]
            )
            if retry_count >= len(retry_intervals):
                return 'retry-given-up'
            elif retry_intervals[retry_count] < retry_celery_cutoff:
                send_webhook.apply_async(args=(logentry_id, action_type, webhook_id, retry_count + 1))
                return 'retry-via-celery'
            else:
                webhook.retries.update_or_create(
                    logentry=logentry,
                    defaults=dict(
                        retry_not_before=now() + timedelta(seconds=retry_intervals[retry_count]),
                        retry_count=retry_count + 1,
                        action_type=action_type,
                    ),
                )
                return 'retry-via-db'


@app.task(base=TransactionAwareTask)
def manually_retry_all_calls(webhook_id: int):
    with scopes_disabled():
        webhook = WebHook.objects.get(id=webhook_id)
    with scope(organizer=webhook.organizer), transaction.atomic():
        for whcr in webhook.retries.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked,
            of=OF_SELF
        ):
            send_webhook.apply_async(
                args=(whcr.logentry_id, whcr.action_type, whcr.webhook_id, whcr.retry_count),
            )
            whcr.delete()


@receiver(signal=periodic_task, dispatch_uid='pretixapi_schedule_webhook_retries_on_celery')
@scopes_disabled()
def schedule_webhook_retries_on_celery(sender, **kwargs):
    with transaction.atomic():
        for whcr in WebHookCallRetry.objects.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked,
            of=OF_SELF
        ).filter(retry_not_before__lt=now()):
            send_webhook.apply_async(
                args=(whcr.logentry_id, whcr.action_type, whcr.webhook_id, whcr.retry_count),
            )
            whcr.delete()
