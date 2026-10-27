#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import (
    TYPE_CHECKING, Callable, Dict, List, Literal, NewType, Optional, Protocol,
    Set, TypeAlias, cast,
)

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from pretix.base.decimal import round_decimal

if TYPE_CHECKING:
    from pretix.base.models import Order, OrderPosition

    PrefetchedOrder = NewType("PrefetchedOrder", Order)
    PrefetchedPosition = NewType("PrefetchedPosition", OrderPosition)
else:
    # use object instead of concrete Models to avoid import loops
    PrefetchedOrder = NewType("PrefetchedOrder", object)
    PrefetchedPosition = NewType("PrefetchedPosition", object)

"""
The cancellation system consists out of two parts, Checks and Rules.

Checks are there to uphold the business logic. For example:
- Giftcards can only be canceled if they weren't used yet
- A ticket can only be canceled if it wasn't checked in yet
- The item can be canceled at all

Checks follow from the business logic of pretix, the activated plugins, as well as the general
configuration of the event - they cannot be configured by the user directly.

The signal `self_service_cancellation_checks` can be used by plugins to provide their own
checks to the cancellation process in the form of CancellationCheck objects.

Rules are the user configurable aspect of the cancellation process.
They have configurable time windows, which item they apply to, if they allow the cancellation and possible fees.
The ruling is stored in a RuleResult.

Both Checks and Rules exist in a per-position and a per-process form.
A PositionRule could add an extra cancellation fee for an Item, while a ProcessRule can add a flat fee
for cancelling at all.

The evaluation of Rules and Checks is handled in `services/cancellation.py`, but follows this schema

When a customer triggers a self service cancellation, we will:
1. Per position, resulting in a `PositionResult` each
    a. Evaluate all per position `CancellationChecks`
    b. Evaluate all per position `CancellationRules` and compute the fees
    c. Choose for each position the cheapest `CancellationRules` position result available

2. Once per process, resulting in a `ProcessResult`
    a. Evaluate all per process `CancellationChecks`
    b. Evaluate all per process `CancellationRules`
    c. Choose the cheapest `CancellationRules` process result available, using the previously generated `ProcessResults`

3. Combine both the `PositionResults` and `ProcessResult` into a `CancellationResult`
"""

PositionSet: TypeAlias = Set["OrderPosition"]


class CheckTypes(models.TextChoices):
    """
    Position checks are applied to each position individually, ensuring that cancellation of this position doesn't
    break any business logic.
    Process checks are applied to the cancellation request at a whole.
    """
    POSITION = "position", _("Order Position Cancellation Check")
    PROCESS = "process", _("Cancellation Process Check")


class PositionCheckFn(Protocol):
    """
    Check to see if an individual position can be canceled.
    """

    def __call__(self, order: PrefetchedOrder, keep: PositionSet, position: PrefetchedPosition,
                 check_ts: datetime.datetime,
                 /) -> Optional[CheckResult]:
        """
        :param order: The order the position is part of. Should be the prefetched object
        :param keep: OrderPositions of this position that are not getting canceled
        :param position: OrderPosition that should be canceled and for which this check should be evaluated
        :param check_ts: The time for which this check should be evaluated
        :return: None if the check doesn't apply otherwise a CheckResult Object
        """
        ...


class ProcessCheckFn(Protocol):
    """
    Check to see if a cancellation request for this Order is possible.
    """

    def __call__(self, order: "PrefetchedOrder", keep: PositionSet, check_ts: datetime.datetime, /) \
            -> Optional[CheckResult]:
        """
        :param order: The Order the cancellation is for
        :param keep: The OrderPositions that aren't getting canceled
        :param check_ts: The time for which this check should be evaluated
        :return:
        """
        ...


@dataclass(frozen=True)
class CancellationCheck:
    """

    """
    id: str
    type: CheckTypes
    check_fn: PositionCheckFn | ProcessCheckFn = field(compare=False)
    prefetches: List[Callable[[], Prefetch]] = field(default_factory=list)
    related_selects: List[str] = field(default_factory=list)

    def evaluate(self, order: PrefetchedOrder, keep: PositionSet,
                 position: "OrderPosition | None", check_ts: datetime.datetime) -> Optional[CheckResult]:
        if position and self.type == CheckTypes.POSITION:
            prefetched_position = cast(PrefetchedPosition,
                                       next((p for p in order.positions.all() if p.pk == position.pk), None))
            if prefetched_position is None:
                raise ValidationError(f"OrderPosition {position.pk} does not belong to order {order.code}")
            return self.check_fn(order, keep, prefetched_position, check_ts)
        elif position is None and self.type == CheckTypes.PROCESS:
            return self.check_fn(order, keep, check_ts)
        else:
            raise ValidationError("Type of the rule doesn't match the check_fn")


@dataclass(frozen=True)
class CheckResult:
    """
    Result of an individual cancellation check.
    """
    id: str
    reason: str
    cancellation_possible: bool
    type: Literal['check'] = field(default="check")

    @classmethod
    def from_dict(cls, data: dict) -> "CheckResult":
        return cls(**data)


class FeeType(models.TextChoices):
    """
    Process fees can be added on top of all position fees, or they
    can set a floor for the minimum cancellation fee that this will incur.
    """
    MINIMUM = "min_process_fee", _("Minimum total fee")
    ADDITIONAL = "add_process_fee", _("Additional fee")
    POSITION = "position_fee", _("Position fee")


@dataclass(frozen=True)
class RuleResult:
    """
    Result of evaluating a CancellationRule.

    A RuleResult encodes both the feasibility of a cancellation via `cancellation_possible` and
    the resulting consequences in form of fees which can be expressed as:
    - absolute position fees of a fixed amount
    - relative position fees of a percentage of the position price
    - minimum process fees, the total cancellation fee across all positions and the process must be at least this
    - additional process fee, an additional processing fee is charged in addition to the per position fees
    """
    id: int
    partial_results: List[CheckResult]
    fee_type: FeeType
    fee: Decimal

    type: Literal['rule'] = field(default="rule")

    @classmethod
    def from_dict(cls, data: dict) -> "RuleResult":
        return cls(
            id=data["id"],
            partial_results=[CheckResult.from_dict(r) for r in data["partial_results"]],
            fee_type=FeeType(data["fee_type"]),
            fee=Decimal(data["fee"]),
        )

    @property
    def cancellation_possible(self) -> bool:
        return all(result.cancellation_possible for result in self.partial_results)

    @classmethod
    def from_absolute_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.POSITION],
            absolute_fee: Decimal
    ) -> "RuleResult":
        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type, fee=absolute_fee)

    @classmethod
    def from_relative_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.POSITION],
            position_price: Decimal,
            percentage: Decimal,
            currency: str
    ) -> "RuleResult":
        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type,
                          fee=round_decimal(position_price * (percentage / 100), currency))

    @classmethod
    def from_process_fee(
            cls,
            id: int,
            partial_results: List[CheckResult],
            fee_type: Literal[FeeType.MINIMUM, FeeType.ADDITIONAL],
            absolute_fee: Decimal,
            reference_price: Decimal
    ) -> "RuleResult":
        if fee_type == FeeType.MINIMUM:
            if reference_price < absolute_fee:
                fee = absolute_fee - reference_price
            else:
                fee = Decimal(0)
        elif fee_type == FeeType.ADDITIONAL:
            fee = absolute_fee
        else:
            raise ValueError("Unknown fee type")

        return RuleResult(id=id, partial_results=partial_results, fee_type=fee_type, fee=fee)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RuleResult):
            return NotImplemented

        if self.cancellation_possible == other.cancellation_possible:
            return self.fee < other.fee
        else:
            return self.cancellation_possible and not other.cancellation_possible


@dataclass(frozen=True)
class PositionResult:
    position_check_results: Dict[int, List[CheckResult]]
    position_rule_results: Dict[int, List[RuleResult]]

    @classmethod
    def from_dict(cls, data: dict) -> "PositionResult":
        return cls(
            position_check_results={
                int(pos_id): [CheckResult.from_dict(r) for r in results]
                for pos_id, results in data["position_check_results"].items()
            },
            position_rule_results={
                int(pos_id): [RuleResult.from_dict(r) for r in results]
                for pos_id, results in data["position_rule_results"].items()
            },
        )

    @property
    def cancellation_possible(self) -> bool:
        def ok(results: List[CheckResult] | List[RuleResult]) -> bool:
            return all([val.cancellation_possible for val in results]) if results else True

        return all(
            ok(results)
            for d in
            (self.position_check_results,
             {key: [min(pos_res)] for key, pos_res in self.position_rule_results.items() if pos_res})
            for results in d.values()
        )

    @property
    def fee_value(self) -> Decimal:
        fee_value = Decimal("0.00")
        for pos_id, results in self.position_rule_results.items():
            if len(results) > 0:
                best_option = min(results)
                if best_option.cancellation_possible:
                    fee_value += best_option.fee
        return fee_value


@dataclass(frozen=True)
class ProcessResult:
    process_check_results: List[CheckResult]
    process_rule_results: List[RuleResult]

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessResult":
        return cls(
            process_check_results=[CheckResult.from_dict(r) for r in data["process_check_results"]],
            process_rule_results=[RuleResult.from_dict(r) for r in data["process_rule_results"]],
        )

    @property
    def cancellation_possible(self) -> bool:
        results: List[CheckResult | RuleResult] = [*self.process_check_results]
        if self.process_rule_results:
            results.append(min(self.process_rule_results))
        return all(res.cancellation_possible for res in results)

    @property
    def fee_value(self) -> Decimal:
        if not self.process_rule_results:
            return Decimal("0.00")
        best_option = min(self.process_rule_results)
        if best_option.cancellation_possible:
            return best_option.fee
        return Decimal("0.00")


@dataclass(frozen=True)
class CancellationResult:
    position_result: PositionResult
    process_result: ProcessResult

    @classmethod
    def from_dict(cls, data: dict) -> "CancellationResult":
        return cls(
            position_result=PositionResult.from_dict(data["position_result"]),
            process_result=ProcessResult.from_dict(data["process_result"]),
        )

    @property
    def cancellation_possible(self) -> bool:
        return self.position_result.cancellation_possible and self.process_result.cancellation_possible
