import json
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.db import transaction
from django.utils.timezone import now

from pretix.base.models import Event, Item, Order, OrderPosition, Organizer


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def event(organizer):
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def webhook(organizer, event):
    wh = organizer.webhooks.create(
        enabled=True,
        target_url='https://google.com',
        all_events=False
    )
    wh.limit_events.add(event)
    wh.listeners.create(action_type='pretix.event.order.placed')
    wh.listeners.create(action_type='pretix.event.order.paid')
    return wh


@pytest.fixture
def order(event):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, locale='en',
        datetime=now(), expires=now() + timedelta(days=10),
        total=Decimal('46.00'),
    )
    tr19 = event.tax_rules.create(rate=Decimal('19.00'))
    ticket = Item.objects.create(event=event, name='Early-bird ticket', tax_rule=tr19,
                                 default_price=Decimal('23.00'), admission=True)
    OrderPosition.objects.create(
        order=o, item=ticket, variation=None,
        price=Decimal("23.00"), attendee_name_parts={'full_name': "Peter"}, positionid=1
    )
    return o


def force_str(v):
    return v.decode() if isinstance(v, bytes) else str(v)


@pytest.fixture
def monkeypatch_on_commit(monkeypatch):
    monkeypatch.setattr("django.db.transaction.on_commit", lambda t: t())


@pytest.mark.django_db
@responses.activate
def test_webhook_trigger_event_specific(event, order, webhook, monkeypatch_on_commit):
    responses.add_callback(
        responses.POST, 'https://google.com',
        callback=lambda r: (200, {}, 'ok'),
        content_type='application/json',
    )

    with transaction.atomic():
        le = order.log_action('pretix.event.order.paid', {})
    assert len(responses.calls) == 1
    assert json.loads(force_str(responses.calls[0].request.body)) == {
        "notification_id": le.pk,
        "organizer": "dummy",
        "event": "dummy",
        "code": "FOO",
        "action": "pretix.event.order.paid"
    }
    first = webhook.calls.last()
    assert first.webhook == webhook
    assert first.target_url == 'https://google.com'
    assert first.action_type == 'pretix.event.order.paid'
    assert not first.is_retry
    assert first.return_code == 200
    assert first.success


@pytest.mark.django_db
@responses.activate
def test_webhook_trigger_global(event, order, webhook, monkeypatch_on_commit):
    webhook.limit_events.clear()
    webhook.all_events = True
    webhook.save()
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        le = order.log_action('pretix.event.order.paid', {})
    assert len(responses.calls) == 1
    assert json.loads(force_str(responses.calls[0].request.body)) == {
        "notification_id": le.pk,
        "organizer": "dummy",
        "event": "dummy",
        "code": "FOO",
        "action": "pretix.event.order.paid"
    }


@pytest.mark.django_db
@responses.activate
def test_webhook_trigger_global_wildcard(event, order, webhook, monkeypatch_on_commit):
    webhook.listeners.create(action_type="pretix.event.order.changed.*")
    webhook.limit_events.clear()
    webhook.all_events = True
    webhook.save()
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        le = order.log_action('pretix.event.order.changed.item', {})
    assert len(responses.calls) == 1
    assert json.loads(force_str(responses.calls[0].request.body)) == {
        "notification_id": le.pk,
        "organizer": "dummy",
        "event": "dummy",
        "code": "FOO",
        "action": "pretix.event.order.changed.item"
    }


@pytest.mark.django_db
@responses.activate
def test_webhook_ignore_wrong_action_type(event, order, webhook, monkeypatch_on_commit):
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        order.log_action('pretix.event.order.changed.item', {})
    assert len(responses.calls) == 0


@pytest.mark.django_db
@responses.activate
def test_webhook_ignore_disabled(event, order, webhook, monkeypatch_on_commit):
    webhook.enabled = False
    webhook.save()
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        order.log_action('pretix.event.order.changed.item', {})
    assert len(responses.calls) == 0


@pytest.mark.django_db
@responses.activate
def test_webhook_ignore_wrong_event(event, order, webhook, monkeypatch_on_commit):
    webhook.limit_events.clear()
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        order.log_action('pretix.event.order.changed.item', {})
    assert len(responses.calls) == 0


@pytest.mark.django_db
@pytest.mark.xfail(reason="retries can't be tested with celery_always_eager")
@responses.activate
def test_webhook_retry(event, order, webhook, monkeypatch_on_commit):
    responses.add(responses.POST, 'https://google.com', status=500)
    responses.add(responses.POST, 'https://google.com', status=200)
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(responses.calls) == 2
    second = webhook.objects.first()
    first = webhook.objects.last()

    assert first.webhook == webhook
    assert first.target_url == 'https://google.com'
    assert first.action_type == 'pretix.event.order.paid'
    assert not first.is_retry
    assert first.return_code == 500
    assert not first.success

    assert second.webhook == webhook
    assert second.target_url == 'https://google.com'
    assert second.action_type == 'pretix.event.order.paid'
    assert first.is_retry
    assert first.return_code == 200
    assert first.success


@pytest.mark.django_db
@responses.activate
def test_webhook_disable_gone(event, order, webhook, monkeypatch_on_commit):
    responses.add(responses.POST, 'https://google.com', status=410)
    with transaction.atomic():
        order.log_action('pretix.event.order.paid', {})
    assert len(responses.calls) == 1
    webhook.refresh_from_db()
    assert not webhook.enabled
