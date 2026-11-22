from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderFee, OrderPayment, OrderPosition, Organizer, Quota,
)
from pretix.base.services.orders import OrderError, _cancel_order
from pretix.control.forms.orders import CancelForm

TOTAL = Decimal('20.00')
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def organizer_scope():
    with scopes_disabled():
        yield


@pytest.fixture
def make_order():
    timestamp = now()
    organizer = Organizer.objects.create(name='Rule tests', slug='rule-tests')
    event = Event.objects.create(
        organizer=organizer, name='Synthetic ticket order', slug='orders',
        currency='EUR', date_from=timestamp + timedelta(days=30),
    )
    event.settings.set('payment_term_accept_late', True)
    event.settings.set('invoice_generate', 'False')
    item = Item.objects.create(event=event, name='Synthetic admission', default_price=TOTAL, admission=True)
    quota = Quota.objects.create(event=event, name='Admission quota', size=10)
    quota.items.add(item)
    channel = organizer.sales_channels.get(identifier='web')

    def create(status=Order.STATUS_PENDING, active_position=True, quota_size=10):
        if quota_size != quota.size:
            quota.size = quota_size
            quota.save(update_fields=['size'])
        order = Order.objects.create(
            event=event, status=status, sales_channel=channel, total=TOTAL,
            email='orders-unit@example.test', locale='en',
            expires=timestamp + timedelta(days=-2 if status == Order.STATUS_EXPIRED else 7),
        )
        if active_position:
            OrderPosition.objects.create(order=order, item=item, price=TOTAL)
        order.create_transactions()
        return order

    return create


@pytest.mark.parametrize(
    'initial,amount,expected',
    [
        pytest.param('n', '20.00', 'p', id='PAY-01-pending-fully-paid'),
        pytest.param('e', '20.00', 'p', id='PAY-02-expired-quota-available'),
        pytest.param('n', '19.99', 'n', id='BR-01-partial-balance-stays-pending'),
        pytest.param('c', '20.00', 'c', id='BR-01-confirmation-does-not-reopen-canceled-order'),
    ],
)
def test_br01_confirmation_updates_order_when_eligible_and_fully_paid(make_order, initial, amount, expected):
    order = make_order(initial)
    payment = order.payments.create(
        state=OrderPayment.PAYMENT_STATE_CREATED, provider='manual', amount=Decimal(amount),
    )

    payment.confirm(send_mail=False)
    payment.refresh_from_db()
    order.refresh_from_db()

    assert order.status == expected
    assert order.total == TOTAL
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert payment.amount == Decimal(amount)
    assert order.positions.count() == 1


def test_br01_confirming_same_payment_twice_preserves_record_and_date(make_order):
    order = make_order()
    payment = order.payments.create(state=OrderPayment.PAYMENT_STATE_CREATED, provider='manual', amount=TOTAL)
    payment.confirm(send_mail=False)
    original_date = payment.payment_date

    payment.confirm(send_mail=False, payment_date=original_date + timedelta(hours=1))
    payment.refresh_from_db()
    order.refresh_from_db()

    assert order.status == Order.STATUS_PAID
    assert list(order.payments.values_list('pk', 'state', 'payment_date')) == [
        (payment.pk, OrderPayment.PAYMENT_STATE_CONFIRMED, original_date),
    ]


def test_br01_expired_order_cannot_be_marked_paid_when_quota_is_full(make_order):
    order = make_order(Order.STATUS_EXPIRED, quota_size=0)
    payment = order.payments.create(state=OrderPayment.PAYMENT_STATE_CREATED, provider='manual', amount=TOTAL)

    with pytest.raises(Quota.QuotaExceededException):
        payment.confirm(send_mail=False)

    order.refresh_from_db()
    assert order.status == Order.STATUS_EXPIRED
    assert order.total == TOTAL
    assert order.positions.count() == 1


@pytest.mark.parametrize('status', ['n', 'e', 'p', 'c'], ids=['pending', 'expired', 'paid', 'canceled'])
@pytest.mark.parametrize('with_position', [True, False], ids=['active-position', 'no-position'])
def test_br02_cancel_allowed_mcc(make_order, status, with_position):
    order = make_order(status, active_position=with_position)

    assert bool(order.cancel_allowed()) is (status in {'n', 'e', 'p'} and with_position)


@pytest.mark.parametrize(
    'initial,active_position',
    [pytest.param('c', True, id='canceled'), pytest.param('n', False, id='positionless')],
)
def test_can04_cancellation_rejects_ineligible_order(make_order, initial, active_position):
    order = make_order(initial, active_position=active_position)

    with pytest.raises(OrderError, match='You cannot cancel this order'):
        _cancel_order(order.pk, send_mail=False, cancellation_fee=Decimal('5.00'))

    order.refresh_from_db()
    assert order.status == initial
    assert order.total == TOTAL
    assert order.positions.count() == int(active_position)
    assert not order.all_fees.exists()


@pytest.mark.parametrize(
    'entered,expected,error',
    [
        ('', '0.00', None),
        ('0.00', '0.00', None),
        ('-0.01', '-0.01', None),
        ('19.99', '19.99', None),
        ('20.00', '20.00', None),
        ('20.01', None, 'The cancellation fee cannot be higher than the total amount of this order.'),
        ('19.999', None, 'Ensure that there are no more than 2 decimal places.'),
    ],
)
def test_br03_cancellation_form_fee_partitions(make_order, entered, expected, error):
    order = make_order()
    form = CancelForm(instance=order, data={'cancellation_fee': entered})

    assert form.is_valid() is (error is None)
    if error:
        assert list(form.errors['cancellation_fee']) == [error]
    else:
        assert form.cleaned_data['cancellation_fee'] == Decimal(expected)


def test_br03_service_rolls_back_when_fee_exceeds_total(make_order):
    order = make_order()
    original_position = order.positions.get()

    with pytest.raises(OrderError, match='cancellation fee cannot be higher'):
        _cancel_order(order.pk, send_mail=False, cancellation_fee=Decimal('20.01'))

    order.refresh_from_db()
    original_position.refresh_from_db()
    assert order.status == Order.STATUS_PENDING
    assert order.total == TOTAL
    assert order.cancellation_date is None
    assert original_position.canceled is False
    assert not order.all_fees.exists()


@pytest.mark.parametrize(
    'initial,fee,expected',
    [
        pytest.param('p', '0.00', 'c', id='CAN-01-paid-no-fee'),
        pytest.param('n', '0.00', 'c', id='BR-04-pending-no-fee'),
        pytest.param('e', '0.00', 'c', id='BR-04-expired-no-fee'),
        pytest.param('p', '19.99', 'p', id='CAN-02-covered-fee-below-total'),
        pytest.param('p', '20.00', 'p', id='CAN-02-covered-fee-at-total'),
        pytest.param('n', '5.00', 'n', id='BR-04-unfunded-fee-stays-pending'),
    ],
)
def test_br04_cancellation_persists_expected_state(make_order, initial, fee, expected):
    order = make_order(initial)
    charge = Decimal(fee)
    position = order.positions.get()
    if initial == Order.STATUS_PAID:
        order.payments.create(
            state=OrderPayment.PAYMENT_STATE_CONFIRMED, provider='manual', amount=TOTAL, payment_date=now(),
        )

    _cancel_order(order.pk, send_mail=False, cancellation_fee=charge)

    order.refresh_from_db()
    position.refresh_from_db()
    assert order.status == expected
    assert order.total == (charge or TOTAL)
    assert position.canceled is bool(charge)
    assert order.cancellation_date is not None
    expected_fees = [(OrderFee.FEE_TYPE_CANCELLATION, charge)] if charge else []
    assert list(order.fees.values_list('fee_type', 'value')) == expected_fees
    expected_payments = [(OrderPayment.PAYMENT_STATE_CONFIRMED, TOTAL)] if initial == Order.STATUS_PAID else []
    assert list(order.payments.values_list('state', 'amount')) == expected_payments
