"""
Placing and paying for a pretix order, checked with due-work-harness.

due-work-harness (https://github.com/gigaverse-app/due-work-harness) is a pytest plugin that checks
background work is neither lost nor run twice. A contract names the guarantees a system offers and binds
each to real code; the harness then generates the test cases.

Two contracts bind what a customer does:

* ``PAYMENT_CONTRACT``: ``OrderPayment.confirm``, which a payment provider's webhook calls when a customer
  has paid;
* ``PLACEMENT_CONTRACT``: ``_perform_order``, which checkout calls to turn a cart into an order.

The harness runs each with the worker dying right after each of its commits, each after-commit callback
failing, and the broker refusing each publish. Recovery is what production runs, ``manage.py runperiodic``,
a month later for payments (after the payment term) and a day later for placement. Each history must end
where normal operation does. What diverges is declared as a gap, a strict xfail, and each history's
``findings`` pin what every run leaves, in the same run as the verdict.

Run it (Python 3.12 or later)::

    pip install -e ".[dev]" psycopg2-binary
    cd src && py.test tests/due_work
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core import mail as djmail
from django.core.management import call_command
from django.utils.timezone import now
from django_scopes import scopes_disabled
from due_work_harness import (
    CallableDelivery, Findings, due_work_contract_suite,
)
from due_work_harness.contract import (
    Adoption, Decline, DueWorkContract, KnownGap, NotApplicable, Profile,
    SafetyContract, SafetyProfile,
)
from due_work_harness.crash_histories import HandoffHistory
from due_work_harness.host import current_host
from pydantic import BaseModel, ConfigDict

from pretix.base.management.commands.runperiodic import Command as RunPeriodic
from pretix.base.models import (
    CartPosition, Event, Item, Order, OrderPayment, OrderPosition, Organizer,
    Quota,
)
from pretix.base.services.orders import _perform_order

#: The payment term of the orders these histories create.
PAYMENT_TERM = timedelta(days=5)

MANUAL_PAYMENT = [
    {
        'id': 'test1', 'provider': 'manual', 'max_value': None, 'min_value': None, 'multi_use_supported': False,
        'info_data': {},
    },
]


def an_event_selling_tickets() -> tuple[Event, Item]:
    # ARRANGE: an event with one ticket in a quota, as pretix's own tests build one.
    organizer = Organizer.objects.create(name='Dummy', slug=f'dummy{Organizer.objects.count()}')
    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy', date_from=now(), plugins='tests.testdummy'
    )
    item = Item.objects.create(event=event, name='Ticket', default_price=23, admission=True)
    Quota.objects.create(name='Test', size=10, event=event).items.add(item)
    return event, item


def mails_to(email: str) -> int:
    """The mails that left pretix for ``email``: Django's outbox, since sent mails are cleaned up later."""
    return sum(email in message.to for message in djmail.outbox)


def runperiodic_a_month_later() -> None:
    # REAL PRODUCTION: cron's `manage.py runperiodic`, after the payment term has passed.
    with current_host().require('frozen_clock')(now() + timedelta(days=30)):
        call_command(RunPeriodic())


def runperiodic_a_day_later() -> None:
    # REAL PRODUCTION: cron's `manage.py runperiodic`, while the order is still within its payment term.
    with current_host().require('frozen_clock')(now() + timedelta(days=1)):
        call_command(RunPeriodic())


class Paid(BaseModel):
    """What the customer and the organiser see of one payment."""

    model_config = ConfigDict(frozen=True)

    payment: str
    order: str
    mails_to_the_customer: int


def a_payment_to_confirm() -> tuple[int, str]:
    # ARRANGE: a pending order for two tickets, with a payment the provider is about to report as paid.
    with scopes_disabled():
        event, item = an_event_selling_tickets()
        email = f'customer-{uuid4().hex[:8]}@example.org'
        order = Order.objects.create(
            status=Order.STATUS_PENDING, event=event, datetime=now() - timedelta(days=5),
            expires=now() + PAYMENT_TERM, total=Decimal('46.00'), email=email,
            sales_channel=event.organizer.sales_channels.get(identifier='web'),
        )
        for _ in range(2):
            OrderPosition.objects.create(order=order, item=item, variation=None, price=23)
        return order.payments.create(provider='manual', amount=order.total).pk, email


def the_provider_reports_it_paid(handle: tuple[int, str]) -> None:
    with scopes_disabled():
        OrderPayment.objects.get(pk=handle[0]).confirm()


def what_the_customer_and_organiser_see(handle: tuple[int, str]) -> Paid:
    # OBSERVE: the payment's state, the order's status, and the mails that reached the customer.
    payment_id, email = handle
    with scopes_disabled():
        payment = OrderPayment.objects.select_related('order').get(pk=payment_id)
        return Paid(payment=payment.state, order=payment.order.status, mails_to_the_customer=mails_to(email))


class Placed(BaseModel):
    """What the customer and the organiser see of one order placed at checkout."""

    model_config = ConfigDict(frozen=True)

    orders: int
    status: str
    mails_to_the_customer: int


def a_cart_ready_to_check_out() -> tuple[int, int, str]:
    # ARRANGE: one ticket in a customer's cart, and the manual payment they chose.
    with scopes_disabled():
        event, item = an_event_selling_tickets()
        cart = CartPosition.objects.create(
            event=event, cart_id=uuid4().hex, item=item, price=23, expires=now() + timedelta(minutes=10)
        )
        return event.pk, cart.pk, f'customer-{uuid4().hex[:8]}@example.org'


def the_customer_places_the_order(handle: tuple[int, int, str]) -> None:
    event_id, cart_id, email = handle
    with scopes_disabled():
        _perform_order(Event.objects.get(pk=event_id), MANUAL_PAYMENT, [cart_id], email, 'en', None, {}, 'web')


def what_the_customer_sees(handle: tuple[int, int, str]) -> Placed:
    # OBSERVE: the orders that exist for the customer, their status, and the mails that reached them.
    _event_id, _cart_id, email = handle
    with scopes_disabled():
        orders = list(Order.objects.filter(email=email))
        return Placed(
            orders=len(orders), status=orders[0].status if orders else 'none', mails_to_the_customer=mails_to(email)
        )


#: What each payment history leaves, pinned in the same run as the verdict; a history not listed reaches
#: normal operation. Every entry is a customer who paid, an order that expired, and no mail.
PAID = Paid(payment='confirmed', order='p', mails_to_the_customer=1)
PAID_AND_EXPIRED = Paid(payment='confirmed', order='e', mails_to_the_customer=0)
PAYMENT_FINDINGS = {
    # FINDING: the payment committed as confirmed; the order is marked paid in a second transaction that
    # never ran. Nothing reconciles the two, a repeated confirmation is ignored, and after the payment term
    # `expire_orders` expires the order the customer has paid for.
    'worker died after commit 1': PAID_AND_EXPIRED,
    'worker died after commit 2': PAID_AND_EXPIRED,
    # FINDING: the same, with no death: the publish of the "payment confirmed" notification raises out of
    # confirm() after the payment committed, so the order is never marked paid.
    'after-commit callback 1 failed': PAID_AND_EXPIRED,
    'the broker refused publication 1': PAID_AND_EXPIRED,
}

CONFIRMED = CallableDelivery(name='pretix runperiodic, a month later', recover=runperiodic_a_month_later)

CONFIRM_A_PAYMENT = HandoffHistory(
    name='confirm a payment',
    arrange=a_payment_to_confirm,
    transition=the_provider_reports_it_paid,
    observe=what_the_customer_and_organiser_see,
    findings=Findings(PAID, PAYMENT_FINDINGS),
)

PAYMENT_CONTRACT = DueWorkContract(
    name='pretix: confirming a payment',
    adoption=Adoption.LEGACY,
    transactional=True,
    profiles={
        Profile.A: KnownGap(
            'no periodic task selects a payment that is confirmed while its order is not paid, and expire_orders '
            'selects on the order alone: it expires the order of a confirmed payment once the payment term passes'
        ),
        Profile.B: Decline('confirm serialises on the payment row (select_for_update); it holds no lease'),
        Profile.C: NotApplicable('confirming a payment calls no external system: the provider has already said'),
        Profile.D: NotApplicable('pretix keeps its orders and payments; nothing here is pruned'),
        Profile.E: NotApplicable('one confirmation settles a payment: confirm ignores a second call by design'),
        Profile.F: KnownGap(
            'no product state records that a confirmed payment still owes its order the paid status, so nothing '
            'can derive the obligation the lost second transaction held'
        ),
    },
    safety=SafetyContract(
        name='pretix: confirming a payment',
        adoption=Adoption.LEGACY,
        profiles={
            SafetyProfile.REPLAY_SAFE_EXECUTION: NotApplicable('confirm ignores a payment that is already confirmed'),
            SafetyProfile.BOUNDED_RETRY: NotApplicable('nothing retries confirm: the provider calls it once per event'),
        },
    ),
    handoffs=(CONFIRM_A_PAYMENT,),
    handoff_delivery=CONFIRMED,
    handoff_gaps={
        'confirm a payment': (
            'confirm() commits the payment as confirmed, then marks the order paid in a second transaction: a '
            'death between them, or a failing after-commit callback or refused publish (the notification of the '
            'confirmation is published in between), leaves the payment confirmed and the order pending, and '
            'expire_orders later expires it (https://github.com/pretix/pretix/issues/6611)'
        ),
    },
)


# This is where the magic happens. The class is empty on purpose: the decorator reads
# PAYMENT_CONTRACT above and generates its tests, bound to pretix's real OrderPayment.confirm and
# `manage.py runperiodic`. No test case is written by hand.
#
# One of the generated cases is how the lost payment was found:
# handoff-confirm a payment-assert_crash_at_every_commit_converges runs confirm() once per thing
# that can go wrong (the process dies after a commit, an after-commit callback fails, the broker
# refuses a publish), lets pretix's periodic tasks run a month later, and compares each run with a
# normal payment. Some end with the payment confirmed and the order expired, so the case fails. The
# contract declares that as a gap, and pins every history in PAYMENT_FINDINGS within the same run,
# so it is reported as a strict XFAIL; the day every history converges, it passes, and the strict
# marker fails the run until the gap is removed.
@due_work_contract_suite(PAYMENT_CONTRACT)
class TestConfirmingAPayment:
    """Every case in this class is generated from PAYMENT_CONTRACT; see the comment above."""


#: What each placement history leaves after recovery a day later; a history not listed reaches normal operation.
PLACED = Placed(orders=1, status='n', mails_to_the_customer=1)
NO_ORDER = Placed(orders=0, status='none', mails_to_the_customer=0)
NO_MAIL = Placed(orders=1, status='n', mails_to_the_customer=0)
PLACEMENT_FINDINGS = {
    # Benign: nothing committed the order yet (commits 1 to 8 are the checkout's own bookkeeping), the
    # customer's cart is intact and they can try again.
    **{f'worker died after commit {k}': NO_ORDER for k in range(1, 9)},
    **{f'after-commit callback {k} failed': NO_ORDER for k in range(1, 9)},
    # FINDING: the order committed and everything after it is lost, or fails: the customer holds an order
    # and never receives its confirmation, the mail that carries the payment instructions.
    'worker died after commit 9': NO_MAIL,
    **{f'after-commit callback {k} failed': NO_MAIL for k in range(9, 13)},
    # FINDING: no death at all. A refused publish raises out of the checkout, so the customer sees an
    # error, and the order exists, its cart already consumed.
    'the broker refused publication 1': NO_MAIL,
    'the broker refused publication 2': NO_MAIL,
}

PLACED_ORDER = CallableDelivery(name='pretix runperiodic, a day later', recover=runperiodic_a_day_later)

PLACE_AN_ORDER = HandoffHistory(
    name='place an order',
    arrange=a_cart_ready_to_check_out,
    transition=the_customer_places_the_order,
    observe=what_the_customer_sees,
    findings=Findings(PLACED, PLACEMENT_FINDINGS),
)

PLACEMENT_CONTRACT = DueWorkContract(
    name='pretix: placing an order',
    adoption=Adoption.LEGACY,
    transactional=True,
    profiles={
        Profile.A: KnownGap(
            'nothing owes the customer their confirmation: no periodic task selects a placed order whose '
            'confirmation mail was never made'
        ),
        Profile.B: Decline('placing an order serialises on the event and quota locks; it holds no lease'),
        Profile.C: NotApplicable('placing an order with a manual payment calls no external system'),
        Profile.D: NotApplicable('pretix keeps its orders; nothing here is pruned'),
        Profile.E: NotApplicable('one checkout writes each order once'),
        Profile.F: KnownGap(
            'no product state records that a placed order still owes its confirmation, so nothing can derive it'
        ),
    },
    safety=SafetyContract(
        name='pretix: placing an order',
        adoption=Adoption.LEGACY,
        profiles={
            SafetyProfile.REPLAY_SAFE_EXECUTION: NotApplicable('a cart is consumed by the order made from it'),
            SafetyProfile.BOUNDED_RETRY: NotApplicable('nothing retries checkout'),
        },
    ),
    handoffs=(PLACE_AN_ORDER,),
    handoff_delivery=PLACED_ORDER,
    handoff_gaps={
        'place an order': (
            'the order commits, then its confirmation, invoice and notifications follow outside any '
            'transaction: a death, a failing after-commit callback or a refused publish there leaves an order '
            'that holds tickets, whose customer never receives its confirmation '
            '(https://github.com/pretix/pretix/issues/6612)'
        ),
    },
)


# The magic again, for checkout: the decorator generates this class's tests from PLACEMENT_CONTRACT,
# bound to pretix's real _perform_order. Its handoff case finds the order that exists without a
# confirmation: the process dies after the order commits, or an after-commit callback fails, or the
# broker refuses a publish, and pretix's periodic tasks never send it.
@due_work_contract_suite(PLACEMENT_CONTRACT)
class TestPlacingAnOrder:
    """Every case in this class is generated from PLACEMENT_CONTRACT; see the comment above."""
