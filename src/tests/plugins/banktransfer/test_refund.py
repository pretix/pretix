import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Order, OrderPayment, OrderRefund, Organizer, Team, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    order = Order.objects.create(
        code='1Z3AS', event=event, email='admin@localhost',
        status=Order.STATUS_PAID,
        datetime=now(), expires=now() + timedelta(days=10),
        total=23
    )
    payment = OrderPayment.objects.create(
        order=order,
        amount=Decimal("23"),
        provider='banktransfer',
        state=OrderPayment.PAYMENT_STATE_CONFIRMED,
        info=json.dumps({
            'payer': "Abc Def",
            'iban': "DE27520521540534534466",
            'bic': "HELADEF1MEG",
        })
    )
    return event, user, payment


@pytest.mark.django_db
def test_perform_refund(client, env):
    event, user, payment = env
    client.login(email='dummy@dummy.dummy', password='dummy')
    assert not OrderRefund.objects.exists()
    url = "/control/event/dummy/dummy/orders/1Z3AS/refund"
    r = client.post(url, {
        f"refund-{payment.id}": "23.00",
        "start-mode": "full",
        "perform": True,
    })
    assert r.status_code == 302
    with scope(organizer=event.organizer):
        assert OrderRefund.objects.exists()
        refund = OrderRefund.objects.first()
        assert refund.payment == payment
        assert refund.info_data == {
            'payer': "Abc Def",
            'iban': "DE27520521540534534466",
            'bic': "HELADEF1MEG",
        }


@pytest.mark.django_db
def test_cannot_perform_refund_with_invalid_iban(client, env):
    event, user, payment = env
    payment.info_data = {
        'payer': "Abc Def",
        'iban': "DE27520521540534534467",  # invalid IBAN
        'bic': "HELADEF1MEG",
    }
    payment.save()
    assert not payment.payment_provider.payment_refund_supported(payment)

    client.login(email='dummy@dummy.dummy', password='dummy')
    url = "/control/event/dummy/dummy/orders/1Z3AS/refund"
    r = client.post(url, {
        f"refund-{payment.id}": "23.00",
        "start-mode": "full",
        "perform": True,
    })
    assert r.status_code == 200  # no successfull POST
    with scope(organizer=event.organizer):
        assert not OrderRefund.objects.exists()
