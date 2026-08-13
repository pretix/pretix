import contextlib
from datetime import timedelta
from decimal import Decimal
from typing import List, Literal, cast

import pytest
from django.db.models import Prefetch
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Checkin, Event, Order, OrderPosition, Organizer,
)
from pretix.base.models.cancellation import (
    CancellationCheck, CancellationRule, CheckResult, Checks, CheckTypes,
    FeeType, PositionResult, ProcessResult, RuleResult,
)
from pretix.base.services.orders import signal_listener_position_not_used
from pretix.helpers import ensure_no_queries


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def item(event):
    return event.items.create(
        name='Ticket',
        category=None, default_price=23,
        admission=True
    )


@pytest.fixture
def checkin_list(event):
    return event.checkin_lists.create(name="foo", consider_tickets_used=True)


@pytest.fixture
def order(event, item):
    o = Order.objects.create(
        code='123456', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING,
        datetime=now(), expires=now() + timedelta(days=10),
        sales_channel=event.organizer.sales_channels.get(identifier="web"),
        total=14, locale='en'
    )
    return o


@pytest.fixture
def order_position(item, order):
    op = OrderPosition.objects.create(
        order=order,
        item=item,
        variation=None,
        price=Decimal("14"),
    )
    return op


def make_check_result(possible: bool, *, id: str = "chk", reason: str = "") -> CheckResult:
    return CheckResult(id=id, reason=reason, cancellation_possible=possible)


def make_rule_result(fee, *, possible: bool = True, fee_type: FeeType = FeeType.POSITION, id: int = 1) -> RuleResult:
    return RuleResult(
        id=id,
        partial_results=[make_check_result(possible)],
        fee_type=fee_type,
        fee=Decimal(fee),
    )


def make_cancellation_check(id: str, type: CheckTypes, result: bool, prefetches=None,
                            related_selects=None) -> CancellationCheck:
    if related_selects is None:
        related_selects = []
    if prefetches is None:
        prefetches = []

    def position_check_fn(_order, _keep, _position):
        return make_check_result(result, id=id)

    def check_fn(_order, _keep):
        return make_check_result(result, id=id)

    if type == CheckTypes.POSITION:
        return CancellationCheck(id, type, position_check_fn, prefetches=prefetches, related_selects=related_selects)
    else:
        return CancellationCheck(id, type, check_fn, prefetches=prefetches, related_selects=related_selects)


@pytest.mark.parametrize("partial_results,expected", [
    ([True], True),
    ([False], False),
    ([True, True], True),
    ([False, False], False),
    ([True, False], False),
])
def test_rule_result_cancellation_possible(partial_results: List[bool], expected: bool):
    check_results = [make_check_result(state) for state in partial_results]

    result = RuleResult(id=1, partial_results=check_results, fee_type=FeeType.POSITION, fee=Decimal(0))
    assert result.cancellation_possible == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (("5", True), ("10", True), True),
        (("10", True), ("5", True), False),
        (("5", True), ("5", True), False),
        (("5", False), ("10", False), True),
        (("100", True), ("1", False), True),
        (("1", False), ("100", True), False),
    ],
    ids=[
        "cheaper-lt-pricier-both-possible",
        "pricier-not-lt-cheaper-both-possible",
        "equal-fee-not-lt",
        "cheaper-lt-pricier-both-impossible",
        "possible-lt-impossible-despite-higher-fee",
        "impossible-not-lt-possible",
    ],
)
def test_lt_returns_expected(left, right, expected):
    a = make_rule_result(left[0], possible=left[1])
    b = make_rule_result(right[0], possible=right[1])
    assert (a < b) is expected


@pytest.mark.parametrize(
    ("fee_type", "absolute", "reference", "result"),
    [
        (FeeType.MINIMUM, Decimal(10), Decimal(1), Decimal(9)),
        (FeeType.MINIMUM, Decimal(1), Decimal(10), Decimal(0)),
        (FeeType.MINIMUM, Decimal(10), Decimal(10), Decimal(0)),
        (FeeType.ADDITIONAL, Decimal(10), Decimal(1), Decimal(10)),
        (FeeType.ADDITIONAL, Decimal(1), Decimal(10), Decimal(1)),
        (FeeType.ADDITIONAL, Decimal(10), Decimal(10), Decimal(10)),
    ],
    ids=[
        "minimum-absolute-less-than-reference",
        "minimum-absolute-more-than-reference",
        "minimum-absolute-equal-reference",
        "additional-absolute-less-than-reference",
        "additional-absolute-more-than-reference",
        "additional-absolute-equal-reference",
    ],
)
def test_from_process_fee(fee_type: Literal[FeeType.MINIMUM, FeeType.ADDITIONAL], absolute: Decimal, reference: Decimal,
                          result: Decimal):
    res = RuleResult.from_process_fee(id=1, partial_results=[],
                                      fee_type=fee_type, absolute_fee=absolute, reference_price=reference)
    assert res.fee == result


@pytest.mark.parametrize(
    ("check_results", "rule_results", "cancellation_possible", "fee"),
    [
        ({1: [make_check_result(True)]}, {1: [make_rule_result(Decimal(10), possible=True)]}, True, Decimal(10)),
        ({1: [make_check_result(False)]}, {1: [make_rule_result(Decimal(10), possible=True)]}, False, Decimal(10)),
        ({1: [make_check_result(False)]}, {1: [make_rule_result(Decimal(10), possible=False)]}, False, Decimal(0)),
        ({1: [make_check_result(True), make_check_result(False)]}, {1: [make_rule_result(Decimal(10), possible=True)]},
         False, Decimal(10)),
        ({1: [make_check_result(True)]},
         {1: [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=True)]}, True,
         Decimal(5)),
        ({1: [make_check_result(True)]},
         {1: [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=False)]}, False,
         Decimal(0)),

    ],
)
def test_position_results(check_results, rule_results, cancellation_possible, fee):
    pos_res = PositionResult(position_check_results=check_results, position_rule_results=rule_results, )
    assert pos_res.cancellation_possible == cancellation_possible
    assert pos_res.fee_value == fee


@pytest.mark.parametrize(
    ("check_results", "rule_results", "cancellation_possible", "fee"),
    [
        ([make_check_result(True)], [make_rule_result(Decimal(10), possible=True)], True, Decimal(10)),
        ([make_check_result(False)], [make_rule_result(Decimal(10), possible=True)], False, Decimal(10)),
        ([make_check_result(False)], [make_rule_result(Decimal(10), possible=False)], False, Decimal(0)),
        ([make_check_result(True), make_check_result(False)], [make_rule_result(Decimal(10), possible=True)],
         False, Decimal(10)),
        ([make_check_result(True)],
         [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=True)], True,
         Decimal(5)),
        ([make_check_result(True)],
         [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=False)], False,
         Decimal(0)),

    ],
)
def test_process_results(check_results, rule_results, cancellation_possible, fee):
    pos_res = ProcessResult(process_check_results=check_results, process_rule_results=rule_results, )
    assert pos_res.cancellation_possible == cancellation_possible
    assert pos_res.fee_value == fee


@pytest.mark.parametrize(
    ("received", "position_checks", "process_checks", "raises"),
    [
        ([('', make_cancellation_check('pos-1', CheckTypes.POSITION, True))],
         [make_cancellation_check('pos-1', CheckTypes.POSITION, True)],
         [],
         contextlib.nullcontext()),
        ([('', make_cancellation_check('proc-1', CheckTypes.PROCESS, True))],
         [],
         [make_cancellation_check('proc-1', CheckTypes.PROCESS, True)],
         contextlib.nullcontext()),
        ([('', make_cancellation_check('proc-1', CheckTypes.PROCESS, True)),
          ('', make_cancellation_check('proc-1', CheckTypes.PROCESS, True))],
         [],
         [make_cancellation_check('proc-1', CheckTypes.PROCESS, True)],
         pytest.raises(ValueError)),
        ([('', make_cancellation_check('pos-1', CheckTypes.POSITION, True)),
          ('', make_cancellation_check('pos-1', CheckTypes.POSITION, True))],
         [],
         [make_cancellation_check('pos-1', CheckTypes.POSITION, True)],
         pytest.raises(ValueError)),
        ([('', 1)],
         [],
         [make_cancellation_check('pos-1', CheckTypes.POSITION, True)],
         pytest.raises(ValueError)),
    ]
)
def test_cancellation_rule_collect_checks(received, position_checks, process_checks, raises):
    event = cast(Event, cast(object, {}))

    def send_fn(_event):
        return received

    with raises:
        checks = CancellationRule._collect_checks(event=event, send_fn=send_fn)
        assert checks.position == position_checks
        assert checks.process == process_checks


@pytest.mark.django_db
def test_prefetch_empty(event, order):
    checks = Checks(position=[], process=[])
    with scope(organizer=event.organizer):
        prefetched_order = CancellationRule._prefetch_order(event, order, checks)
        assert prefetched_order.id == order.id


@pytest.mark.django_db
def test_prefetch_incl_values_select_related(event, order):
    checks = Checks(
        position=[
            make_cancellation_check('pos_1', CheckTypes.POSITION, True, prefetches=[lambda: Prefetch('all_positions')],
                                    related_selects=['organizer'])],
        process=[
            make_cancellation_check('proc_1', CheckTypes.PROCESS, True, prefetches=[lambda: Prefetch('all_positions')],
                                    related_selects=['organizer'])]
    )

    with scope(organizer=event.organizer):
        prefetched_order = CancellationRule._prefetch_order(event, order, checks)
        assert prefetched_order.id == order.id


@pytest.mark.django_db
def test_ticket_not_used(event, order, order_position, checkin_list):
    position_not_used_check = signal_listener_position_not_used(event)
    checks = Checks(position=[position_not_used_check], process=[])
    keep = set()

    with scope(organizer=event.organizer):
        prefetched_order = CancellationRule._prefetch_order(event, order, checks)
        with ensure_no_queries():
            result = position_not_used_check.evaluate(prefetched_order, keep, order_position)
        assert result.cancellation_possible is True

        Checkin.objects.create(
            list=checkin_list,
            position=order_position,
            successful=True
        )
        prefetched_order = CancellationRule._prefetch_order(event, order, checks)

        with ensure_no_queries():
            result = position_not_used_check.evaluate(prefetched_order, keep, order_position)

        assert result.cancellation_possible is False
