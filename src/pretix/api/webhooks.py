import json
import logging
import time
from collections import OrderedDict

import requests
from celery.exceptions import MaxRetriesExceededError
from django.db.models import Exists, OuterRef, Q
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _
from django_scopes import scope, scopes_disabled
from requests import RequestException

from pretix.api.models import WebHook, WebHookCall, WebHookEventListener
from pretix.api.signals import register_webhook_events
from pretix.base.models import LogEntry
from pretix.base.services.tasks import ProfiledTask, TransactionAwareTask
from pretix.celery_app import app

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


class ParametrizedOrderWebhookEvent(WebhookEvent):
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

    def build_payload(self, logentry: LogEntry):
        order = logentry.content_object

        return {
            'notification_id': logentry.pk,
            'organizer': order.event.organizer.slug,
            'event': order.event.slug,
            'code': order.code,
            'action': logentry.action_type,
        }


class ParametrizedOrderPositionWebhookEvent(ParametrizedOrderWebhookEvent):

    def build_payload(self, logentry: LogEntry):
        d = super().build_payload(logentry)
        d['orderposition_id'] = logentry.parsed_data.get('position')
        d['orderposition_positionid'] = logentry.parsed_data.get('positionid')
        d['checkin_list'] = logentry.parsed_data.get('list')
        d['first_checkin'] = logentry.parsed_data.get('first_checkin')
        return d


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
            'pretix.event.order.refund.created.externally',
            _('External refund of payment'),
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
    )


@app.task(base=TransactionAwareTask)
def notify_webhooks(logentry_id: int):
    logentry = LogEntry.all.get(id=logentry_id)

    if not logentry.organizer:
        return  # We need to know the organizer

    types = get_all_webhook_events()
    notification_type = None
    typepath = logentry.action_type
    while not notification_type and '.' in typepath:
        notification_type = types.get(typepath + ('.*' if typepath != logentry.action_type else ''))
        typepath = typepath.rsplit('.', 1)[0]

    if not notification_type:
        return  # Ignore, no webhooks for this event type

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
        send_webhook.apply_async(args=(logentry_id, notification_type.action_type, wh.pk))


@app.task(base=ProfiledTask, bind=True, max_retries=9)
def send_webhook(self, logentry_id: int, action_type: str, webhook_id: int):
    # 9 retries with 2**(2*x) timing is roughly 72 hours
    with scopes_disabled():
        webhook = WebHook.objects.get(id=webhook_id)
    with scope(organizer=webhook.organizer):
        logentry = LogEntry.all.get(id=logentry_id)
        types = get_all_webhook_events()
        event_type = types.get(action_type)
        if not event_type or not webhook.enabled:
            return  # Ignore, e.g. plugin not installed

        payload = event_type.build_payload(logentry)
        t = time.time()

        try:
            try:
                resp = requests.post(
                    webhook.target_url,
                    json=payload,
                    allow_redirects=False
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
                elif resp.status_code > 299:
                    raise self.retry(countdown=2 ** (self.request.retries * 2))
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
                raise self.retry(countdown=2 ** (self.request.retries * 2))
        except MaxRetriesExceededError:
            pass
