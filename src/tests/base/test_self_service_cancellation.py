from decimal import Decimal

import pytest

from pretix.base.models.cancellation import CheckResult, FeeType, RuleResult


def make_check(possible: bool, *, id: str = "chk", reason: str = "") -> CheckResult:
    return CheckResult(id=id, reason=reason, cancellation_possible=possible)


def make_rule(fee, *, possible: bool = True, fee_type: FeeType = FeeType.POSITION, id: int = 1) -> RuleResult:
    # ``cancellation_possible`` is derived from the partial check results, so we
    # attach a single passing/failing check to control it deterministically.
    return RuleResult(
        id=id,
        partial_results=[make_check(possible)],
        fee_type=fee_type,
        fee=Decimal(fee),
    )


@pytest.mark.parametrize("partial_results,expected", [
    ([True], True),
    ([False], False),
    ([True, True], True),
    ([False, False], False),
    ([True, False], False),
])
def test_rule_result_cancellation_possible(partial_results, expected):
    check_results = [make_check(state) for state in partial_results]

    result = RuleResult(id=1, partial_results=check_results, fee_type=FeeType.POSITION, fee=Decimal(0))
    assert result.cancellation_possible == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (("5", True), ("10", True), True),  # cheaper fee is "less"
        (("10", True), ("5", True), False),  # pricier fee is not "less"
        (("5", True), ("5", True), False),  # equal fee is not "less"
        (("5", False), ("10", False), True),  # cheaper is "less" when both impossible
        (("100", True), ("1", False), True),  # possible ranks below impossible...
        (("1", False), ("100", True), False),  # ...and impossible never below possible
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
    a = make_rule(left[0], possible=left[1])
    b = make_rule(right[0], possible=right[1])
    assert (a < b) is expected
