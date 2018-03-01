import datetime

import pytest
from django.utils.timezone import now

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, Organizer, Quota,
)
from pretix.testutils.sessions import add_cart_session, get_cart_session_key


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.paypal',
        live=True
    )
    category = ItemCategory.objects.create(event=event, name="Everything", position=0)
    quota_tickets = Quota.objects.create(event=event, name='Tickets', size=5)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=category, default_price=23, admission=True)
    quota_tickets.items.add(ticket)
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_paypal__enabled', True)
    event.settings.set('payment_paypal__fee_abs', 3)
    event.settings.set('payment_paypal_endpoint', 'sandbox')
    event.settings.set('payment_paypal_client_id', '12345')
    event.settings.set('payment_paypal_secret', '12345')
    add_cart_session(client, event, {'email': 'admin@localhost'})
    return client, ticket


@pytest.mark.django_db
def test_payment(env, monkeypatch):
    def create_payment(self, request, payment):
        assert payment['intent'] == 'sale'
        assert payment['transactions'][0]['amount']['currency'] == 'EUR'
        assert payment['transactions'][0]['amount']['total'] == '26.00'
        create_payment.called = True
        return 'https://approve.url'
    monkeypatch.setattr("pretix.plugins.paypal.payment.Paypal._create_payment", create_payment)

    client, ticket = env
    session_key = get_cart_session_key(client, ticket.event)
    CartPosition.objects.create(
        event=ticket.event, cart_id=session_key, item=ticket,
        price=23, expires=now() + datetime.timedelta(minutes=10)
    )
    client.get('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), follow=True)
    client.post('/%s/%s/checkout/questions/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'email': 'admin@localhost'
    }, follow=True)
    response = client.post('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'payment': 'paypal'
    })
    assert response['Location'] == 'https://approve.url'
