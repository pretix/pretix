"""Member 3 controlled failure-and-recovery tests for the Orders workflows.

Each test makes a dependency fail through a test double (unittest.mock.patch) before a state-changing write
completes, re-reads the persisted state from the database, restores the dependency, retries, and asserts the
expected final state without duplicate business records.

SQLite ignores select_for_update, so these tests show transactional atomicity, not lock-based concurrency safety.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderFee, OrderPayment, OrderPosition, Organizer, Quota,
)
from pretix.base.services.orders import OrderError, _cancel_order

TOTAL = Decimal('20.00')
FEE = Decimal('5.00')
pytestmark = pytest.mark.django_db


class DependencyUnavailable(ConnectionError):
    """Raised by the test doubles to simulate an unavailable dependency."""


@pytest.fixture(autouse=True)
def organizer_scope():
    with scopes_disabled():
        yield


@pytest.fixture
def make_order():
    timestamp = now()
    organizer = Organizer.objects.create(name='Recovery tests', slug='recovery-tests')
    event = Event.objects.create(
        organizer=organizer, name='Synthetic recovery event', slug='orders',
        currency='EUR', date_from=timestamp + timedelta(days=30),
    )
    event.settings.set('invoice_generate', 'False')
    item = Item.objects.create(event=event, name='Synthetic admission', default_price=TOTAL, admission=True)
    Quota.objects.create(event=event, name='Admission quota', size=10).items.add(item)
    channel = organizer.sales_channels.get(identifier='web')

    def create(status=Order.STATUS_PENDING, paid=False):
        order = Order.objects.create(
            event=event, status=status, sales_channel=channel, total=TOTAL,
            email='recovery@example.test', locale='en', expires=timestamp + timedelta(days=7),
        )
        OrderPosition.objects.create(order=order, item=item, price=TOTAL)
        if paid:
            order.payments.create(
                provider='manual', amount=TOTAL, state=OrderPayment.PAYMENT_STATE_CONFIRMED, payment_date=timestamp,
            )
        order.create_transactions()
        return order

    return create


def snapshot(order_pk):
    """Fresh read of every record the workflows change. Never trust in-memory objects after a failure."""
    order = Order.objects.get(pk=order_pk)
    return {
        'status': order.status,
        'total': order.total,
        'cancellation_date_set': order.cancellation_date is not None,
        'positions_active': order.all_positions.filter(canceled=False).count(),
        'positions_canceled': order.all_positions.filter(canceled=True).count(),
        'cancellation_fees': order.fees.filter(fee_type=OrderFee.FEE_TYPE_CANCELLATION).count(),
        'confirmed_payments': list(
            order.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED).values_list('amount', flat=True)
        ),
        'transactions': order.transactions.count(),
    }


# ---------------------------------------------------------------- W2 cancellation with a retained fee


@pytest.mark.parametrize('failure_point', [
    # Fails before the first database write: shows that nothing partial is stored when a dependency is down
    # early. (A sensitivity probe showed this case still passes with the transaction removed.)
    pytest.param('pretix.base.services.orders.assign_ticket_secret', id='REC-01-secret-generator-before-first-write'),
    # Fails after the order, positions and fee were written: only the atomic block in _cancel_order can undo
    # them, so this case is the atomicity check (it fails when transaction.atomic is replaced by a no-op).
    pytest.param('pretix.base.models.Order.create_transactions', id='REC-01b-ledger-after-writes-atomic-rollback'),
])
def test_rec01_cancellation_rolls_back_completely_and_retry_has_no_duplicates(make_order, failure_point):
    order = make_order(Order.STATUS_PAID, paid=True)
    before = snapshot(order.pk)
    assert before['status'] == Order.STATUS_PAID and before['positions_active'] == 1

    # 1. Dependency fails part-way through the cancellation write.
    with patch(failure_point, side_effect=DependencyUnavailable('dependency unavailable')):
        with pytest.raises(DependencyUnavailable):
            _cancel_order(order.pk, cancellation_fee=FEE, send_mail=False)

    # 2. Persisted state after the failure is exactly the state before it (REC-01: nothing written yet;
    #    REC-01b: the writes already made are rolled back by the atomic block).
    assert snapshot(order.pk) == before

    # 3. Dependency restored: retry the same operation.
    _cancel_order(order.pk, cancellation_fee=FEE, send_mail=False)
    after = snapshot(order.pk)
    assert after['status'] == Order.STATUS_PAID  # 20.00 paid covers the 5.00 retained fee
    assert after['total'] == FEE
    assert after['cancellation_date_set'] is True
    assert after['positions_active'] == 0
    assert after['positions_canceled'] == 1
    assert after['cancellation_fees'] == 1
    assert after['confirmed_payments'] == [TOTAL]

    # 4. A repeated request is rejected and creates no second fee.
    with pytest.raises(OrderError):
        _cancel_order(order.pk, cancellation_fee=FEE, send_mail=False)
    assert snapshot(order.pk) == after


# ---------------------------------------------------------------- W1 payment confirmation

def _audit_log_down_for(action_name):
    """Test double: the audit-log store rejects one specific action and accepts all others."""
    original = Order.log_action

    def flaky(self, action, *args, **kwargs):
        if action == action_name:
            raise DependencyUnavailable(f'audit log unavailable for {action}')
        return original(self, action, *args, **kwargs)

    return patch.object(Order, 'log_action', flaky)


def _fail_confirmation(make_order):
    order = make_order(Order.STATUS_PENDING)
    payment = order.payments.create(state=OrderPayment.PAYMENT_STATE_CREATED, provider='manual', amount=TOTAL)
    with _audit_log_down_for('pretix.event.order.paid'):
        with pytest.raises(DependencyUnavailable):
            payment.confirm(send_mail=False)
    return order, OrderPayment.objects.get(pk=payment.pk)


def test_rec02_payment_failure_after_confirmation_persists_a_partial_state(make_order):
    order, payment = _fail_confirmation(make_order)

    # Observed persisted state: confirm() commits the payment in its own transaction before marking the order
    # paid, so the failure leaves a confirmed payment on an order that is still pending (hypothesis H4).
    state = snapshot(order.pk)
    assert payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED
    assert state['status'] == Order.STATUS_PENDING
    assert state['confirmed_payments'] == [TOTAL]


@pytest.mark.xfail(strict=True, reason='H4: retrying confirm() on an already-confirmed payment returns early, '
                                       'so the order stays pending. See the GitHub issue linked in recovery.md.')
def test_rec02b_retrying_the_same_confirmation_completes_the_order(make_order):
    order, payment = _fail_confirmation(make_order)
    payment.confirm(send_mail=False)  # dependency restored, same operation retried
    assert snapshot(order.pk)['status'] == Order.STATUS_PAID


def test_rec02c_manual_recovery_marks_order_paid_without_a_duplicate_payment(make_order):
    order, payment = _fail_confirmation(make_order)

    # Recovery path used by the control panel when nothing is outstanding (OrderTransition.post, amount 0.00):
    # it re-runs the "mark order paid" step on the last confirmed payment instead of creating a new one.
    order.refresh_from_db()
    assert order.pending_sum <= Decimal('0.00')
    payment._mark_order_paid(send_mail=False, payment_refund_sum=order.payment_refund_sum)

    after = snapshot(order.pk)
    assert after['status'] == Order.STATUS_PAID
    assert after['confirmed_payments'] == [TOTAL]
    assert OrderPayment.objects.filter(order_id=order.pk).count() == 1
