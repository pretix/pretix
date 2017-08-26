import datetime

import pytest
from django.conf import settings
from django.utils.timezone import now

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, Organizer, Quota,
)


class MockedCharge():
    def __init__(self):
        self.status = ''
        self.paid = False
        self.id = 'ch_123345345'

    def refresh(self):
        pass


@pytest.fixture
def env(client):
    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.stripe',
        live=True
    )
    category = ItemCategory.objects.create(event=event, name="Everything", position=0)
    quota_tickets = Quota.objects.create(event=event, name='Tickets', size=5)
    ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                 category=category, default_price=23, admission=True)
    quota_tickets.items.add(ticket)
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_stripe__enabled', True)
    client.session.email = 'admin@localhost'
    return client, ticket


@pytest.mark.django_db
def test_payment(env, monkeypatch):
    def charge_create(**kwargs):
        assert kwargs['amount'] == 1337
        assert kwargs['currency'] == 'eur'
        assert kwargs['source'] == 'tok_189fTT2eZvKYlo2CvJKzEzeu'
        c = MockedCharge()
        c.status = 'succeeded'
        c.paid = True
        charge_create.called = True
        return c
    monkeypatch.setattr("stripe.Charge.create", charge_create)

    client, ticket = env
    session_key = client.cookies.get(settings.SESSION_COOKIE_NAME).value
    CartPosition.objects.create(
        event=ticket.event, cart_id=session_key, item=ticket,
        price=13.37, expires=now() + datetime.timedelta(minutes=10)
    )
    client.get('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), follow=True)
    client.post('/%s/%s/checkout/questions/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'email': 'admin@localhost'
    }, follow=True)
    charge_create.called = False
    response = client.post('/%s/%s/checkout/payment/' % (ticket.event.organizer.slug, ticket.event.slug), {
        'payment': 'stripe',
        'stripe_token': 'tok_189fTT2eZvKYlo2CvJKzEzeu',
        'stripe_card_brand': 'visa',
        'stripe_card_last4': '1234'
    }, follow=True)
    assert not charge_create.called
    assert response.status_code == 200
    assert 'alert-danger' not in response.rendered_content
    response = client.post('/%s/%s/checkout/confirm/' % (ticket.event.organizer.slug, ticket.event.slug), {
    }, follow=True)
    assert charge_create.called
    assert response.status_code == 200
