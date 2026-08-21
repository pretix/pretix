import contextlib
from datetime import UTC, timedelta, datetime
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
    FeeType, PositionCancellationRule, PositionResult, ProcessCancellationRule, ProcessResult, RuleResult,
)
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
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
                            related_selects=None,
                            check_ts: datetime = datetime.now(tz=UTC)) -> CancellationCheck:
    if related_selects is None:
        related_selects = []
    if prefetches is None:
        prefetches = []

    def position_check_fn(_order, _keep, _position, _check_ts=check_ts):
        return make_check_result(result, id=id)

    def check_fn(_order, _keep, _check_ts=check_ts):
        return make_check_result(result, id=id)

    if type == CheckTypes.POSITION:
        return CancellationCheck(id, type, position_check_fn, prefetches=prefetches, related_selects=related_selects)
    else:
        return CancellationCheck(id, type, check_fn, prefetches=prefetches, related_selects=related_selects)


class TestRuleResult:
    @pytest.mark.parametrize("partial_results,expected", [
        ([True], True),
        ([False], False),
        ([True, True], True),
        ([False, False], False),
        ([True, False], False),
    ])
    def test_rule_result_cancellation_possible(self, partial_results: List[bool], expected: bool):
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
    def test_lt_returns_expected(self, left, right, expected):
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
    def test_from_process_fee(
            self,
            fee_type: Literal[FeeType.MINIMUM, FeeType.ADDITIONAL],
            absolute: Decimal,
            reference: Decimal,
            result: Decimal
    ):
        res = RuleResult.from_process_fee(id=1, partial_results=[],
                                          fee_type=fee_type, absolute_fee=absolute, reference_price=reference)
        assert res.fee == result

    @pytest.mark.parametrize(
        ("position_price", "percentage", "result"),
        [
            (Decimal(10), Decimal(10), Decimal(1)),
            (Decimal(10), Decimal("9.9"), Decimal("0.99"))
        ],
    )
    def test_from_relative_fee(self, position_price, percentage, result):
        res = RuleResult.from_relative_fee(id=1,
                                           partial_results=[],
                                           fee_type=FeeType.POSITION,
                                           position_price=position_price,
                                           percentage=percentage,
                                           currency="EUR")
        assert res.fee == result


class TestPositionResult:
    @pytest.mark.parametrize(
        ("check_results", "rule_results", "cancellation_possible", "fee"),
        [
            ({1: [make_check_result(True)]}, {1: [make_rule_result(Decimal(10), possible=True)]}, True, Decimal(10)),
            ({1: [make_check_result(False)]}, {1: [make_rule_result(Decimal(10), possible=True)]}, False, Decimal(10)),
            ({1: [make_check_result(False)]}, {1: [make_rule_result(Decimal(10), possible=False)]}, False, Decimal(0)),
            ({1: [make_check_result(True), make_check_result(False)]},
             {1: [make_rule_result(Decimal(10), possible=True)]},
             False, Decimal(10)),
            ({1: [make_check_result(True)]},
             {1: [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=True)]}, True,
             Decimal(5)),
            ({1: [make_check_result(True)]},
             {1: [make_rule_result(Decimal(10), possible=False), make_rule_result(Decimal(5), possible=False)]}, False,
             Decimal(0)),

        ],
    )
    def test_position_results(self, check_results, rule_results, cancellation_possible, fee):
        pos_res = PositionResult(position_check_results=check_results, position_rule_results=rule_results, )
        assert pos_res.cancellation_possible == cancellation_possible
        assert pos_res.fee_value == fee

    def test_position_with_no_rule_results_does_not_raise(self):
        # A position that has check results but no matching rule results at all
        # must not blow up min() on [].
        check_results = {1: [make_check_result(True)]}
        rule_results = {1: []}

        pos_res = PositionResult(position_check_results=check_results, position_rule_results=rule_results)

        assert pos_res.cancellation_possible is True
        assert pos_res.fee_value == Decimal(0)

    def test_mixed_positions_one_without_rule_results(self):
        # One position has rules, another has none.
        # The empty one shouldn't crash the overall evaluation or affect the other.
        check_results = {1: [make_check_result(True)], 2: []}
        rule_results = {1: [make_rule_result(Decimal(10), possible=True)], 2: []}

        pos_res = PositionResult(position_check_results=check_results, position_rule_results=rule_results)

        assert pos_res.cancellation_possible is True
        assert pos_res.fee_value == Decimal(10)

class TestProcessResults:
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
    def test_process_results(self, check_results, rule_results, cancellation_possible, fee):
        pos_res = ProcessResult(process_check_results=check_results, process_rule_results=rule_results, )
        assert pos_res.cancellation_possible == cancellation_possible
        assert pos_res.fee_value == fee

    def test_process_with_no_rules_configured_does_not_raise(self):
        # No ProcessCancellationRule configured for the event at all: process_rule_results == [].
        # Should be treated as "no process fee, doesn't block cancellation", not crash.
        check_results = [make_check_result(True)]
        rule_results = []

        proc_res = ProcessResult(process_check_results=check_results, process_rule_results=rule_results)

        assert proc_res.cancellation_possible is True
        assert proc_res.fee_value == Decimal("0.00")

    def test_process_with_no_rules_but_failing_check(self):
        # Empty rule_results shouldn't mask a failing check-based result.
        check_results = [make_check_result(False)]
        rule_results = []

        proc_res = ProcessResult(process_check_results=check_results, process_rule_results=rule_results)

        assert proc_res.cancellation_possible is False
        assert proc_res.fee_value == Decimal("0.00")


class TestCancellationRule:
    @pytest.mark.parametrize(
        ("received", "position_checks", "process_checks", "raises"),
        [
            (
                    [make_cancellation_check('pos-1', CheckTypes.POSITION, True)],
                    [0],
                    [],
                    contextlib.nullcontext()
            ),
            (
                    [make_cancellation_check('proc-1', CheckTypes.PROCESS, True)],
                    [],
                    [0],
                    contextlib.nullcontext()
            ),
            (
                    [make_cancellation_check('pos-1', CheckTypes.POSITION, True),
                     make_cancellation_check('proc-1', CheckTypes.PROCESS, True)],
                    [0],
                    [1],
                    contextlib.nullcontext()
            ),
            (
                    [make_cancellation_check('proc-1', CheckTypes.PROCESS, True),
                     make_cancellation_check('proc-1', CheckTypes.PROCESS, True)],
                    [],
                    [],
                    pytest.raises(ValueError)
            ),
            (
                    [make_cancellation_check('pos-1', CheckTypes.POSITION, True),
                     make_cancellation_check('pos-1', CheckTypes.POSITION, True)],
                    [],
                    [],
                    pytest.raises(ValueError)
            ),
            (
                    [('', 1)],
                    [],
                    [],
                    pytest.raises(ValueError)
            ),
        ]
    )
    def test_cancellation_rule_collect_checks(self, received, position_checks, process_checks, raises):
        event = cast(Event, cast(object, {}))

        def send_fn(_event):
            return [("", res) for res in received]

        with raises:
            checks = CancellationRule._collect_checks(event=event, send_fn=send_fn)

        for pos in process_checks:
            assert received[pos] in checks.process

        for pos in position_checks:
            assert received[pos] in checks.position

    class TestPrefetching:

        @pytest.mark.django_db
        def test_prefetch_no_checks_collected(self, event, order):
            checks = Checks(position=[], process=[])
            with scope(organizer=event.organizer):
                prefetched_order = CancellationRule._prefetch_order(event, order, checks)
                assert prefetched_order.id == order.id

        @pytest.mark.django_db
        def test_prefetch_incl_values_select_related(self, event, order):
            checks = Checks(
                position=[
                    make_cancellation_check('pos_1', CheckTypes.POSITION, True,
                                            prefetches=[lambda: Prefetch('all_positions')],
                                            related_selects=['organizer'])],
                process=[
                    make_cancellation_check('proc_1', CheckTypes.PROCESS, True,
                                            prefetches=[lambda: Prefetch('all_positions')],
                                            related_selects=['organizer'])]
            )

            with scope(organizer=event.organizer):
                prefetched_order = CancellationRule._prefetch_order(event, order, checks)
                assert prefetched_order.id == order.id

    class TestChecks:

        @pytest.mark.django_db
        def test_ticket_not_used(self, event, order, order_position, checkin_list):
            position_not_used_check = signal_listener_position_not_used(event)
            checks = Checks(position=[position_not_used_check], process=[])
            keep = set()

            with scope(organizer=event.organizer):
                prefetched_order = CancellationRule._prefetch_order(event, order, checks)
                with ensure_no_queries():
                    result = position_not_used_check.evaluate(prefetched_order, keep, order_position,
                                                              datetime.now(tz=UTC))
                assert result.cancellation_possible is True

                Checkin.objects.create(
                    list=checkin_list,
                    position=order_position,
                    successful=True
                )
                prefetched_order = CancellationRule._prefetch_order(event, order, checks)

                with ensure_no_queries():
                    result = position_not_used_check.evaluate(prefetched_order, keep, order_position,
                                                              datetime.now(tz=UTC))

                assert result.cancellation_possible is False

    class TestResolveDateFields:

        REFERENCE_DT = datetime(2017, 12, 27, 4, 0, 0, tzinfo=UTC)

        @pytest.fixture(params=["date", "datetime", "order", "event"])
        def rdt_reldate_variants(self, request):
            return request.param

        @pytest.fixture
        def rdt_reldate(self, rdt_reldate_variants) -> RelativeDateWrapper:
            if rdt_reldate_variants == 'date' or rdt_reldate_variants == 'datetime':
                return RelativeDateWrapper.from_string(self.REFERENCE_DT.isoformat())
            elif rdt_reldate_variants == 'order':
                return RelativeDateWrapper(
                    RelativeDate(days=1, time=None, base_date_name='order__datetime', minutes=None, is_after=True))
            elif rdt_reldate_variants == 'event':
                return RelativeDateWrapper(
                    RelativeDate(days=1, time=None, base_date_name='event__date_from', minutes=None, is_after=True))
            else:
                raise ValueError()

        @pytest.fixture(params=["single_event", "subevents"])
        def rdt_event_variants(self, request):
            return request.param

        @pytest.fixture
        def rdt_events(self, rdt_event_variants, event):
            if rdt_event_variants == "single_event":
                event.date_from = self.REFERENCE_DT
                event.save()
            else:
                event.has_subevents = True
                event.subevents.create(
                    name='1',
                    date_from=self.REFERENCE_DT,
                )
                event.subevents.create(
                    name='2',
                    date_from=self.REFERENCE_DT + timedelta(days=1),
                )
                event.subevents.create(
                    name='3',
                    date_from=self.REFERENCE_DT + timedelta(days=2),
                )
            return event

        @pytest.fixture
        def rdt_item(self, rdt_events):
            return rdt_events.items.create(
                name='Ticket',
                category=None, default_price=23,
                admission=True
            )

        @pytest.fixture(params=["EARLIEST", "LATEST"])
        def rdt_mode_variants(self, request):
            return request.param

        @pytest.fixture
        def rdt_order(self, rdt_events):
            o = Order.objects.create(
                code='123456', event=rdt_events, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=self.REFERENCE_DT + timedelta(hours=6),  # 6 hours offset mark orders
                sales_channel=rdt_events.organizer.sales_channels.get(identifier="web"),
                total=14, locale='en'
            )
            return o

        @pytest.fixture
        def rdt_order_positions(self, rdt_event_variants, rdt_events, rdt_item, rdt_order):
            if rdt_event_variants == "single_event":
                op = [OrderPosition.objects.create(
                    order=rdt_order,
                    item=rdt_item,
                    variation=None,
                    price=Decimal("14"),
                )]
            else:
                op = []
                for i in range(0, 3):
                    op.append(OrderPosition.objects.create(
                        subevent=rdt_events.subevents.all()[i],
                        order=rdt_order,
                        item=rdt_item,
                        variation=None,
                        price=Decimal("14"),
                    ))
            return op

        @pytest.mark.django_db
        def test_process_rule_resolve_date_field(
                self,
                rdt_reldate,
                rdt_reldate_variants,
                rdt_events,
                rdt_event_variants,
                rdt_mode_variants,
                rdt_order,
                rdt_order_positions
        ):
            with scope(organizer=rdt_events.organizer):
                date = ProcessCancellationRule._resolve_date_field(rdt_reldate, rdt_order, rdt_mode_variants)
                match rdt_reldate_variants:
                    case "date":
                        assert date == self.REFERENCE_DT
                    case "datetime":
                        assert date == self.REFERENCE_DT
                    case "order":
                        assert date == self.REFERENCE_DT + timedelta(days=1) + timedelta(hours=6)
                    case "event":
                        if rdt_event_variants == "single_event":
                            assert date == self.REFERENCE_DT + timedelta(days=1)
                        elif rdt_event_variants == "subevents":
                            if rdt_mode_variants == "EARLIEST":
                                assert date == self.REFERENCE_DT + timedelta(days=1)
                            elif rdt_mode_variants == "LATEST":
                                assert date == self.REFERENCE_DT + timedelta(days=1) + timedelta(days=2)
                            else:
                                raise ValueError("Variant not known")
                        else:
                            raise ValueError("Variant not known")
                    case _:
                        raise ValueError("Variant not known")

        @pytest.mark.django_db
        def test_position_rule_resolve_date_field(
                self,
                rdt_reldate,
                rdt_reldate_variants,
                rdt_events,
                rdt_event_variants,
                rdt_order,
                rdt_order_positions
        ):
            with scope(organizer=rdt_events.organizer):
                for pos in rdt_order_positions:
                    date = PositionCancellationRule._resolve_date_field(rdt_reldate, rdt_order, pos)
                    match rdt_reldate_variants:
                        case "date":
                            assert date == self.REFERENCE_DT
                        case "datetime":
                            assert date == self.REFERENCE_DT
                        case "order":
                            assert date == self.REFERENCE_DT + timedelta(days=1) + timedelta(hours=6)
                        case "event":
                            if rdt_event_variants == "single_event":
                                assert date == self.REFERENCE_DT + timedelta(days=1)
                            elif rdt_event_variants == "subevents":
                                assert date == pos.subevent.date_from + timedelta(days=1)
                            else:
                                raise ValueError("Variant not known")
                        case _:
                            raise ValueError("Variant not known")

    class TestPositionMatchesRule:
        @pytest.fixture
        def items(self, event):
            return [event.items.create(
                name='Product 1',
                category=None, default_price=23,
                admission=True
            ), event.items.create(
                name='Product 2',
                category=None, default_price=23,
                admission=True
            )]

        @pytest.fixture
        def variations(self, event, items):
            item = items[0]
            return [
                item.variations.create(
                    value="Variation 1"
                ),
                item.variations.create(
                    value="Variation 2"
                ),

            ]

        @pytest.mark.django_db
        @pytest.mark.parametrize(
            ("item_idx", "variation_idx", "all_products", "limit_products", "limit_variations", "matches"),
            [
                (0, None, True, [], [], True),
                (0, 0, True, [], [], True),
                (0, 1, True, [], [], True),
                (1, None, True, [], [], True),
                (0, None, False, [], [], False),
                (0, 0, False, [], [], False),
                (0, 1, False, [], [], False),
                (1, None, False, [], [], False),
                (0, None, False, [0], [], True),
                (1, None, False, [0], [], False),
                (0, None, False, [1], [], False),
                (0, 0, False, [0], [0], True),
                (1, None, False, [0], [0], False),
                (0, 1, False, [1], [], False),
                (0, 0, False, [0], [0, 1], True),
            ],
            ids=[
                "all_products::item-0",
                "all_products::item-0-variation-0",
                "all_products::item-0-variation-1",
                "all_products::item-1",
                "no-product::item-0",
                "no-product::item-0-variation-0",
                "no-product::item-0-variation-1",
                "no-product::item-1",
                "item-0::item-0",
                "item-0::item-1",
                "item-1::item-0",
                "item-0-variation-0::item-0-variation-0",
                "item-0-variation-0::item-1",
                "item-1::item-0-variation-1",
                "item-0-variation-0-variation-1::item-0-variation-0",

            ]

        )
        def test_position_matches_rule(self, event, order, items, variations, item_idx,
                                       variation_idx, all_products, limit_products, limit_variations,
                                       matches):
            with scope(organizer=event.organizer):
                op = OrderPosition.objects.create(
                    order=order,
                    item=items[item_idx],
                    variation=variations[variation_idx] if variation_idx is not None else None,
                    price=Decimal("14"),
                )
                r = PositionCancellationRule.objects.create(event=event, all_products=all_products)
                for lp in limit_products:
                    r.limit_products.add(items[lp])
                for lv in limit_variations:
                    r.limit_variations.add(variations[lv])

                rule = PositionCancellationRule.objects.with_rule_data().get(id=r.id)
                with ensure_no_queries():
                    res = rule._position_matches_rule(op)
                if not matches:
                    assert res is None
                else:
                    assert matches == res.cancellation_possible

    class TestEvaluateCancellationMoment:
        @pytest.fixture(params=["position", "process"])
        def rule_type_variants(self, request):
            return request.param

        @pytest.mark.django_db
        @pytest.mark.parametrize(
            ('attr', "delta", "allowed"),
            [
                ('allowed_until', timedelta(hours=-1), True),
                ('allowed_until', timedelta(hours=0), True),
                ('allowed_until', timedelta(hours=+1), False),
                ('except_after', timedelta(hours=-1), True),
                ('except_after', timedelta(hours=0), True),
                ('except_after', timedelta(hours=+1), False)

            ]
        )
        def test_evaluate_cancellation_moment(self, event, order, order_position, rule_type_variants, attr, delta,
                                              allowed):
            reference_ts = datetime(2020, 10, 1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)

            with scope(organizer=event.organizer):
                if rule_type_variants == 'position':
                    rule_object = PositionCancellationRule
                    r = rule_object.objects.create(event=event, all_products=True)
                elif rule_type_variants == "process":
                    rule_object = ProcessCancellationRule
                    r = rule_object.objects.create(event=event, all_products=True, fee_mode=FeeType.MINIMUM)
                else:
                    raise ValueError("Unknown cancellation rule type: {}".format(rule_type_variants))


                setattr(r, attr, RelativeDateWrapper(reference_ts))
                r.save()
                rule = rule_object.objects.get(id=r.id)

                with ensure_no_queries():
                    if rule_type_variants == 'position':
                        res = rule._evaluate_cancellation_moment(position=order_position, check_ts=reference_ts + delta)
                    elif rule_type_variants == "process":
                        res = rule._evaluate_cancellation_moment(order=order,
                                                                 check_ts=reference_ts + delta)
                    else:
                        raise ValueError("Unknown cancellation rule type: {}".format(rule_type_variants))

            assert len(res) == 2
            for r in res:
                if attr in r.id:
                    assert r.cancellation_possible == allowed

    class TestEvaluate:
        # TODO add more elaborate test cases

        @pytest.mark.django_db
        def test_evaluate_simple_e2e(self, event, order, order_position):
            reference_ts = datetime(2020, 10, 1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)

            check_ts = reference_ts - timedelta(hours=1)

            PositionCancellationRule.objects.create(event=event, all_products=True,
                                                    fee_absolute_per_position=Decimal("10.00"),
                                                    allowed_until=RelativeDateWrapper(reference_ts))
            PositionCancellationRule.objects.create(event=event, all_products=True,
                                                    fee_absolute_per_position=Decimal("10.00"),
                                                    allowed_until=RelativeDateWrapper(reference_ts - timedelta(days=1)))
            ProcessCancellationRule.objects.create(event=event, fee_cancellation_process=Decimal("10.00"),
                                                   fee_mode=FeeType.ADDITIONAL,
                                                   allowed_until=RelativeDateWrapper(reference_ts))
            ProcessCancellationRule.objects.create(event=event, fee_cancellation_process=Decimal("10.00"),
                                                   fee_mode=FeeType.ADDITIONAL,
                                                   allowed_until=RelativeDateWrapper(reference_ts - timedelta(days=1)))

            with scope(organizer=event.organizer):
                res = CancellationRule.evaluate(event, order, keep=set(), check_ts=check_ts)

            assert res.cancellation_possible == True

            position_rule_results = res.position_result.position_rule_results[1]
            assert len(position_rule_results) == 2
            assert position_rule_results[0].cancellation_possible == True
            assert position_rule_results[1].cancellation_possible == False

            process_rule_results = res.process_result.process_rule_results
            assert len(process_rule_results) == 2
            assert process_rule_results[0].cancellation_possible == True
            assert process_rule_results[1].cancellation_possible == False
