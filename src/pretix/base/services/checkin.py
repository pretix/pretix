#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import os
from datetime import datetime, timedelta, timezone
from functools import partial, reduce

import dateutil
import dateutil.parser
from dateutil.tz import datetime_exists
from django.core.files import File
from django.db import IntegrityError, transaction
from django.db.models import (
    BooleanField, Count, ExpressionWrapper, F, IntegerField, Max, Min,
    OuterRef, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce, TruncDate
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now, override
from django.utils.translation import gettext as _
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    Checkin, CheckinList, Device, Event, ItemVariation, Order, OrderPosition,
    QuestionOption,
)
from pretix.base.signals import checkin_created, order_placed, periodic_task
from pretix.helpers import OF_SELF
from pretix.helpers.jsonlogic import Logic
from pretix.helpers.jsonlogic_boolalg import convert_to_dnf
from pretix.helpers.jsonlogic_query import (
    Equal, GreaterEqualThan, GreaterThan, InList, LowerEqualThan, LowerThan,
    MinutesSince, tolerance,
)


def _build_time(t=None, value=None, ev=None, now_dt=None):
    now_dt = now_dt or now()
    if t == "custom":
        return dateutil.parser.parse(value)
    elif t == "customtime":
        parsed = dateutil.parser.parse(value)
        return now_dt.astimezone(ev.timezone).replace(
            hour=parsed.hour,
            minute=parsed.minute,
            second=parsed.second,
            microsecond=parsed.microsecond,
        )
    elif t == 'date_from':
        return ev.date_from
    elif t == 'date_to':
        return ev.date_to or ev.date_from
    elif t == 'date_admission':
        return ev.date_admission or ev.date_from


def _logic_annotate_for_graphic_explain(rules, ev, rule_data, now_dt):
    logic_environment = _get_logic_environment(ev, now_dt)
    event = ev if isinstance(ev, Event) else ev.event

    def _evaluate_inners(r):
        if not isinstance(r, dict):
            return r
        operator = list(r.keys())[0]
        values = r[operator]
        if operator in ("and", "or"):
            return {operator: [_evaluate_inners(v) for v in values]}
        result = logic_environment.apply(r, rule_data)
        return {**r, '__result': result}

    def _add_var_values(r):
        if not isinstance(r, dict):
            return r
        operator = [k for k in r.keys() if not k.startswith("__")][0]
        values = r[operator]
        if operator == "var":
            var = values[0] if isinstance(values, list) else values
            val = rule_data[var]
            if var == "product":
                val = str(event.items.get(pk=val))
            elif var == "variation":
                val = str(ItemVariation.objects.get(item__event=event, pk=val))
            elif isinstance(val, datetime):
                val = date_format(val.astimezone(ev.timezone), "SHORT_DATETIME_FORMAT")
            return {"var": var, "__result": val}
        else:
            return {**r, operator: [_add_var_values(v) for v in values]}

    return _add_var_values(_evaluate_inners(rules))


def _logic_explain(rules, ev, rule_data, now_dt=None):
    """
    Explains when the logic denied the check-in. Only works for a denied check-in.

    While our custom check-in logic is very flexible, its main problem is that it is pretty
    intransparent during execution. If the logic causes an entry to be forbidden, the result
    of the logic evaluation is just a simple ``False``, which is very unhelpful to explain to
    attendees why they don't get into the event.

    The main problem with fixing this is that there is no correct answer for this, it is always
    up for interpretation. A good example is the following set of rules:

    - Attendees with a regular ticket can enter the venue between 09:00 and 17:00 on three days
    - Attendees with a VIP ticket can enter the venue between 08:00 and 18:00 on three days

    If an attendee with a regular ticket now shows up at 17:30 on the first day, there are three
    possible error messages:

    a) You do not have a VIP ticket
    b) You can only get in before 17:00
    c) You can only get in after 09:00 tomorrow

    All three of them are just as valid, and "fixing" either one of them would get the attendee in.
    Showing all three is too much, especially since the list can get very long with complex logic.

    We therefore make an opinionated choice based on a number of assumptions. An example for these
    assumptions is "it is very unlikely that the attendee is unable to change their ticket type".
    Additionally, we favor a "close failure". Therefore, in the above example, we'd show "You can only
    get in before 17:00". In the middle of the night it would switch to "You can only get in after 09:00".
    """
    now_dt = now_dt or now()
    logic_environment = _get_logic_environment(ev, now_dt)
    _var_values = {'False': False, 'True': True}
    _var_explanations = {}

    # Step 1: To simplify things later, we replace every operator of the rule that
    # is NOT a boolean operator (AND and OR in our case) with the evaluation result.
    def _evaluate_inners(r):
        if r is True:
            return {'var': 'True'}
        if r is False:
            return {'var': 'False'}
        if not isinstance(r, dict):
            return r
        operator = list(r.keys())[0]
        values = r[operator]
        if operator in ("and", "or"):
            return {operator: [_evaluate_inners(v) for v in values]}
        result = logic_environment.apply(r, rule_data)
        new_var_name = f'v{len(_var_values)}'
        _var_values[new_var_name] = result
        if not result:
            # Operator returned false, let's dig deeper
            if "var" not in values[0]:
                raise ValueError("Binary operators should be normalized to have a variable on their left-hand side")
            if isinstance(values[0]["var"], list):
                values[0]["var"] = values[0]["var"][0]
            _var_explanations[new_var_name] = {
                'operator': operator,
                'var': values[0]["var"],
                'rhs': values[1:],
            }
        return {'var': new_var_name}
    try:
        rules = _evaluate_inners(rules)
    except ValueError:
        return _('Unknown reason')

    # Step 2: Transform the the logic into disjunctive normal form (max. one level of ANDs nested in max. one level
    # of ORs), e.g. `(a AND b AND c) OR (d AND e)`
    rules = convert_to_dnf(rules)

    # Step 3: Split into the various paths to truthiness, e.g. ``[[a, b, c], [d, e]]`` for our sample above
    paths = []
    if "and" in rules:
        # only one path
        paths.append([v["var"] for v in rules["and"]])
    elif "or" in rules:
        # multiple paths
        for r in rules["or"]:
            if "and" in r:
                paths.append([v["var"] for v in r["and"]])
            else:
                paths.append([r["var"]])
    else:
        # only one expression on only one path
        paths.append([rules["var"]])

    # Step 4: For every variable with value False, compute a weight. The weight is a 2-tuple of numbers.
    # The first component indicates a "rigidness level". The higher the rigidness, the less likely it is that the
    # outcome is determined by some action of the attendee. For example, the number of entries has a very low
    # rigidness since the attendee decides how often they enter. The current time has a medium rigidness
    # since the attendee decides when they show up. The product has a high rigidness, since customers usually
    # can't change what type of ticket they have.
    # The second component indicates the "error size". For example for a date comparision this would be the number of
    # seconds between the two dates.
    # Additionally, we compute a text for every variable.
    var_weights = {
        'False': (100000, 0),  # used during testing
        'True': (100000, 0),  # used during testing
    }
    var_texts = {
        'False': 'Always false',  # used during testing
        'True': 'Always true',  # used during testing
    }
    for vname, data in _var_explanations.items():
        var, operator, rhs = data['var'], data['operator'], data['rhs']
        if var == 'now':
            compare_to = _build_time(*rhs[0]['buildTime'], ev=ev, now_dt=now_dt).astimezone(ev.timezone)
            tolerance = timedelta(minutes=float(rhs[1])) if len(rhs) > 1 and rhs[1] else timedelta(seconds=0)
            if operator == 'isBefore':
                compare_to += tolerance
            else:
                compare_to -= tolerance

            var_weights[vname] = (200, abs(now_dt - compare_to).total_seconds())

            if abs(now_dt - compare_to) < timedelta(hours=12):
                compare_to_text = date_format(compare_to, 'TIME_FORMAT')
            else:
                compare_to_text = date_format(compare_to, 'SHORT_DATETIME_FORMAT')
            if operator == 'isBefore':
                var_texts[vname] = _('Only allowed before {datetime}').format(datetime=compare_to_text)
            elif operator == 'isAfter':
                var_texts[vname] = _('Only allowed after {datetime}').format(datetime=compare_to_text)
        elif var == 'product' or var == 'variation':
            var_weights[vname] = (1000, 0)
            var_texts[vname] = _('Ticket type not allowed')
        elif var in ('entries_number', 'entries_today', 'entries_days', 'minutes_since_last_entry', 'minutes_since_first_entry', 'now_isoweekday'):
            w = {
                'minutes_since_first_entry': 80,
                'minutes_since_last_entry': 90,
                'entries_days': 100,
                'entries_number': 120,
                'entries_today': 140,
                'now_isoweekday': 210,
            }
            operator_weights = {
                '==': 2,
                '<': 1,
                '<=': 1,
                '>': 1,
                '>=': 1,
                '!=': 3,
            }
            l = {
                'minutes_since_last_entry': _('time since last entry'),
                'minutes_since_first_entry': _('time since first entry'),
                'entries_days': _('number of days with an entry'),
                'entries_number': _('number of entries'),
                'entries_today': _('number of entries today'),
                'now_isoweekday': _('week day'),
            }
            compare_to = rhs[0]
            penalty = 0

            if var in ('minutes_since_last_entry', 'minutes_since_first_entry'):
                is_comparison_to_minus_one = (
                    (operator == '<' and compare_to <= 0) or
                    (operator == '<=' and compare_to < 0) or
                    (operator == '>=' and compare_to < 0) or
                    (operator == '>' and compare_to <= 0) or
                    (operator == '==' and compare_to == -1) or
                    (operator == '!=' and compare_to == -1)
                )
                if is_comparison_to_minus_one:
                    # These are "technical" comparisons without real meaning, we don't want to show them.
                    penalty = 1000

            var_weights[vname] = (w[var] + operator_weights.get(operator, 0) + penalty, abs(compare_to - rule_data[var]))

            if var == 'now_isoweekday':
                compare_to = {
                    1: _('Monday'),
                    2: _('Tuesday'),
                    3: _('Wednesday'),
                    4: _('Thursday'),
                    5: _('Friday'),
                    6: _('Saturday'),
                    7: _('Sunday'),
                }.get(compare_to, compare_to)

            if operator == '==':
                var_texts[vname] = _('{variable} is not {value}').format(variable=l[var], value=compare_to)
            elif operator in ('<', '<='):
                var_texts[vname] = _('Maximum {variable} exceeded').format(variable=l[var])
            elif operator in ('>', '>='):
                var_texts[vname] = _('Minimum {variable} exceeded').format(variable=l[var])
            elif operator == '!=':
                var_texts[vname] = _('{variable} is {value}').format(variable=l[var], value=compare_to)

        else:
            raise ValueError(f'Unknown variable {var}')

    # Step 5: For every path, compute the maximum weight
    path_weights = [
        max([
            var_weights[v] for v in path if not _var_values[v]
        ] or [(0, 0)]) for path in paths
    ]

    # Step 6: Find the paths with the minimum weight
    min_weight = min(path_weights)
    paths_with_min_weight = [
        p for i, p in enumerate(paths) if path_weights[i] == min_weight
    ]

    # Step 7: All things equal, prefer shorter explanations
    paths_with_min_weight.sort(
        key=lambda p: len([v for v in p if not _var_values[v]])
    )

    # Finally, return the text for one of them
    return ', '.join(var_texts[v] for v in paths_with_min_weight[0] if not _var_values[v])


def _get_logic_environment(ev, now_dt):
    # Every change to our supported JSON logic must be done
    # * in pretix.base.services.checkin
    # * in pretix.base.models.checkin
    # * in checkinrules.js
    # * in libpretixsync

    def is_before(t1, t2, tolerance=None):
        if tolerance:
            return t1 < t2 + timedelta(minutes=float(tolerance))
        else:
            return t1 < t2

    logic = Logic()
    logic.add_operation('objectList', lambda *objs: list(objs))
    logic.add_operation('lookup', lambda model, pk, str: int(pk))
    logic.add_operation('inList', lambda a, b: a in b)
    logic.add_operation('buildTime', partial(_build_time, ev=ev, now_dt=now_dt))
    logic.add_operation('isBefore', is_before)
    logic.add_operation('isAfter', lambda t1, t2, tol=None: is_before(t2, t1, tol))
    return logic


class LazyRuleVars:
    def __init__(self, position, clist, dt):
        self._position = position
        self._clist = clist
        self._dt = dt

    def __getitem__(self, item):
        if item[0] != '_' and hasattr(self, item):
            return getattr(self, item)
        raise KeyError()

    @property
    def now(self):
        return self._dt

    @property
    def now_isoweekday(self):
        tz = self._clist.event.timezone
        return self._dt.astimezone(tz).isoweekday()

    @property
    def product(self):
        return self._position.item_id

    @property
    def variation(self):
        return self._position.variation_id

    @cached_property
    def entries_number(self):
        return self._position.checkins.filter(type=Checkin.TYPE_ENTRY, list=self._clist).count()

    @cached_property
    def entries_today(self):
        tz = self._clist.event.timezone
        midnight = self._dt.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        return self._position.checkins.filter(type=Checkin.TYPE_ENTRY, list=self._clist, datetime__gte=midnight).count()

    @cached_property
    def entries_days(self):
        tz = self._clist.event.timezone
        with override(tz):
            return self._position.checkins.filter(list=self._clist, type=Checkin.TYPE_ENTRY).annotate(
                day=TruncDate('datetime', tzinfo=tz)
            ).values('day').distinct().count()

    @cached_property
    def minutes_since_last_entry(self):
        tz = self._clist.event.timezone
        with override(tz):
            last_entry = self._position.checkins.filter(list=self._clist, type=Checkin.TYPE_ENTRY).order_by('datetime').last()
            if last_entry is None:
                # Returning "None" would be "correct", but the handling of "None" in JSON logic is inconsistent
                # between platforms (None<1 is true on some, but not all), we rather choose something that is at least
                # consistent.
                return -1
            return (self._dt - last_entry.datetime).total_seconds() // 60

    @cached_property
    def minutes_since_first_entry(self):
        tz = self._clist.event.timezone
        with override(tz):
            last_entry = self._position.checkins.filter(list=self._clist, type=Checkin.TYPE_ENTRY).order_by('datetime').first()
            if last_entry is None:
                # Returning "None" would be "correct", but the handling of "None" in JSON logic is inconsistent
                # between platforms (None<1 is true on some, but not all), we rather choose something that is at least
                # consistent.
                return -1
            return (self._dt - last_entry.datetime).total_seconds() // 60


class SQLLogic:
    """
    This is a simplified implementation of JSON logic that creates a Q-object to be used in a QuerySet.
    It does not implement all operations supported by JSON logic and makes a few simplifying assumptions,
    but all that can be created through our graphical editor. There's also CheckinList.validate_rules()
    which tries to validate the same preconditions for rules set through the API (probably not perfect).

    Assumptions:

    * Only a limited set of operators is used
    * The top level operator is always a boolean operation (and, or) or a comparison operation (==, !=, …)
    * Expression operators (var, lookup, buildTime) do not require further recursion
    * Comparison operators (==, !=, …) never contain boolean operators (and, or) further down in the stack
    """

    def __init__(self, list):
        self.list = list
        self.bool_ops = {
            "and": lambda *args: reduce(lambda total, arg: total & arg, args) if args else Q(),
            "or": lambda *args: reduce(lambda total, arg: total | arg, args) if args else Q(),
        }
        self.comparison_ops = {
            "==": partial(self.comparison_to_q, operator=Equal),
            "!=": partial(self.comparison_to_q, operator=Equal, negate=True),
            ">": partial(self.comparison_to_q, operator=GreaterThan),
            ">=": partial(self.comparison_to_q, operator=GreaterEqualThan),
            "<": partial(self.comparison_to_q, operator=LowerThan),
            "<=": partial(self.comparison_to_q, operator=LowerEqualThan),
            "inList": partial(self.comparison_to_q, operator=InList),
            "isBefore": partial(self.comparison_to_q, operator=LowerThan, modifier=partial(tolerance, sign=1)),
            "isAfter": partial(self.comparison_to_q, operator=GreaterThan, modifier=partial(tolerance, sign=-1)),
        }
        self.expression_ops = {'buildTime', 'objectList', 'lookup', 'var'}

    def operation_to_expression(self, rule):
        if not isinstance(rule, dict):
            return rule

        operator = list(rule.keys())[0]
        values = rule[operator]

        if not isinstance(values, list) and not isinstance(values, tuple):
            values = [values]

        if operator == 'buildTime':
            if values[0] == "custom":
                return Value(dateutil.parser.parse(values[1]).astimezone(timezone.utc))
            elif values[0] == "customtime":
                parsed = dateutil.parser.parse(values[1])
                return Value(now().astimezone(self.list.event.timezone).replace(
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=parsed.second,
                    microsecond=parsed.microsecond,
                ).astimezone(timezone.utc))
            elif values[0] == 'date_from':
                return Coalesce(
                    F('subevent__date_from'),
                    F('order__event__date_from'),
                )
            elif values[0] == 'date_to':
                return Coalesce(
                    F('subevent__date_to'),
                    F('subevent__date_from'),
                    F('order__event__date_to'),
                    F('order__event__date_from'),
                )
            elif values[0] == 'date_admission':
                return Coalesce(
                    F('subevent__date_admission'),
                    F('subevent__date_from'),
                    F('order__event__date_admission'),
                    F('order__event__date_from'),
                )
            else:
                raise ValueError(f'Unknown time type {values[0]}')
        elif operator == 'objectList':
            return [self.operation_to_expression(v) for v in values]
        elif operator == 'lookup':
            return int(values[1])
        elif operator == 'var':
            if values[0] == 'now':
                return Value(now().astimezone(timezone.utc))
            elif values[0] == 'now_isoweekday':
                return Value(now().astimezone(self.list.event.timezone).isoweekday())
            elif values[0] == 'product':
                return F('item_id')
            elif values[0] == 'variation':
                return F('variation_id')
            elif values[0] == 'entries_number':
                return Coalesce(
                    Subquery(
                        Checkin.objects.filter(
                            position_id=OuterRef('pk'),
                            type=Checkin.TYPE_ENTRY,
                            list_id=self.list.pk
                        ).values('position_id').order_by().annotate(
                            c=Count('*')
                        ).values('c')
                    ),
                    Value(0),
                    output_field=IntegerField()
                )
            elif values[0] == 'entries_today':
                midnight = now().astimezone(self.list.event.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
                return Coalesce(
                    Subquery(
                        Checkin.objects.filter(
                            position_id=OuterRef('pk'),
                            type=Checkin.TYPE_ENTRY,
                            list_id=self.list.pk,
                            datetime__gte=midnight,
                        ).values('position_id').order_by().annotate(
                            c=Count('*')
                        ).values('c')
                    ),
                    Value(0),
                    output_field=IntegerField()
                )
            elif values[0] == 'entries_days':
                tz = self.list.event.timezone
                return Coalesce(
                    Subquery(
                        Checkin.objects.filter(
                            position_id=OuterRef('pk'),
                            type=Checkin.TYPE_ENTRY,
                            list_id=self.list.pk,
                        ).annotate(
                            day=TruncDate('datetime', tzinfo=tz)
                        ).values('position_id').order_by().annotate(
                            c=Count('day', distinct=True)
                        ).values('c')
                    ),
                    Value(0),
                    output_field=IntegerField()
                )
            elif values[0] == 'minutes_since_last_entry':
                sq_last_entry = Subquery(
                    Checkin.objects.filter(
                        position_id=OuterRef('pk'),
                        type=Checkin.TYPE_ENTRY,
                        list_id=self.list.pk,
                    ).values('position_id').order_by().annotate(
                        m=Max('datetime')
                    ).values('m')
                )

                return Coalesce(
                    MinutesSince(sq_last_entry),
                    Value(-1),
                    output_field=IntegerField()
                )
            elif values[0] == 'minutes_since_first_entry':
                sq_last_entry = Subquery(
                    Checkin.objects.filter(
                        position_id=OuterRef('pk'),
                        type=Checkin.TYPE_ENTRY,
                        list_id=self.list.pk,
                    ).values('position_id').order_by().annotate(
                        m=Min('datetime')
                    ).values('m')
                )

                return Coalesce(
                    MinutesSince(sq_last_entry),
                    Value(-1),
                    output_field=IntegerField()
                )
        else:
            raise ValueError(f'Unknown operator {operator}')

    def comparison_to_q(self, a, b, *args, operator, negate=False, modifier=None):
        a = self.operation_to_expression(a)
        b = self.operation_to_expression(b)
        if modifier:
            b = modifier(b, *args)
        q = Q(
            ExpressionWrapper(
                operator(
                    a,
                    b,
                ),
                output_field=BooleanField()
            )
        )
        return ~q if negate else q

    def apply(self, tests):
        """
        Convert JSON logic to queryset info, returns an Q object and fills self.annotations
        """
        if not tests:
            return Q()
        if isinstance(tests, bool):
            # not really a legal configuration but used in the test suite
            return Value(tests, output_field=BooleanField())

        operator = list(tests.keys())[0]
        values = tests[operator]

        # Easy syntax for unary operators, like {"var": "x"} instead of strict
        # {"var": ["x"]}
        if not isinstance(values, list) and not isinstance(values, tuple):
            values = [values]

        if operator in self.bool_ops:
            return self.bool_ops[operator](*[self.apply(v) for v in values])
        elif operator in self.comparison_ops:
            return self.comparison_ops[operator](*values)
        else:
            raise ValueError(f'Invalid operator {operator} on first level')


class CheckInError(Exception):
    def __init__(self, msg, code, reason=None):
        self.msg = msg
        self.code = code
        self.reason = reason
        super().__init__(msg)


class RequiredQuestionsError(Exception):
    def __init__(self, msg, code, questions):
        self.msg = msg
        self.code = code
        self.questions = questions
        super().__init__(msg)


def _save_answers(op, answers, given_answers):
    def _create_answer(question, answer):
        try:
            return op.answers.create(question=question, answer=answer)
        except IntegrityError:
            # Since we prefill ``field.answer`` at form creation time, there's a possible race condition
            # here if the user submits their scan a second time while the first one is still running,
            # thus leading to duplicate QuestionAnswer objects. Since Django doesn't support UPSERT, the "proper"
            # fix would be a transaction with select_for_update(), or at least fetching using get_or_create here
            # again. However, both of these approaches have a significant performance overhead for *all* requests,
            # while the issue happens very very rarely. So we opt for just catching the error and retrying properly.
            qa = op.answers.get(question=question)
            qa.answer = answer
            qa.save(update_fields=['answer'])
            qa.options.clear()

    written = False
    for q, a in given_answers.items():
        if not a:
            if q in answers:
                written = True
                answers[q].delete()
            else:
                continue
        if isinstance(a, QuestionOption):
            if q in answers:
                qa = answers[q]
                qa.answer = str(a.answer)
                qa.save()
                written = True
                qa.options.clear()
            else:
                qa = _create_answer(question=q, answer=str(a.answer))
            qa.options.add(a)
        elif isinstance(a, list):
            if q in answers:
                qa = answers[q]
                qa.answer = ", ".join([str(o) for o in a])
                qa.save()
                written = True
                qa.options.clear()
            else:
                qa = _create_answer(question=q, answer=", ".join([str(o) for o in a]))
            qa.options.add(*a)
        elif isinstance(a, File):
            if q in answers:
                qa = answers[q]
            else:
                qa = _create_answer(question=q, answer=str(a))
            qa.file.save(os.path.basename(a.name), a, save=False)
            qa.answer = 'file://' + qa.file.name
            qa.save()
            written = True
        else:
            if q in answers:
                qa = answers[q]
                qa.answer = str(a)
                qa.save()
            else:
                _create_answer(question=q, answer=str(a))
            written = True

    if written:
        prefetched_objects_cache = getattr(op, '_prefetched_objects_cache', {})
        if 'answers' in prefetched_objects_cache:
            del prefetched_objects_cache['answers']


def perform_checkin(op: OrderPosition, clist: CheckinList, given_answers: dict, force=False,
                    ignore_unpaid=False, nonce=None, datetime=None, questions_supported=True,
                    user=None, auth=None, canceled_supported=False, type=Checkin.TYPE_ENTRY,
                    raw_barcode=None, raw_source_type=None, from_revoked_secret=False, simulate=False):
    """
    Create a checkin for this particular order position and check-in list. Fails with CheckInError if the check in is
    not valid at this time.

    :param op: The order position to check in
    :param clist: The order position to check in
    :param given_answers: A dictionary of questions mapped to validated, given answers
    :param force: When set to True, this will succeed even when the position is already checked in or when required
        questions are not filled out.
    :param ignore_unpaid: When set to True, this will succeed even when the order is unpaid.
    :param questions_supported: When set to False, questions are ignored
    :param nonce: A random nonce to prevent race conditions.
    :param datetime: The datetime of the checkin, defaults to now.
    :param simulate: If true, the check-in is not saved.
    """

    # !!!!!!!!!
    # Update doc/images/checkin_online.puml if you make substantial changes here!
    # !!!!!!!!!

    dt = datetime or now()
    force_used = False

    if op.canceled or op.order.status not in (Order.STATUS_PAID, Order.STATUS_PENDING):
        if force:
            force_used = True
        else:
            raise CheckInError(
                _('This order position has been canceled.'),
                'canceled' if canceled_supported else 'unpaid'
            )

    if op.blocked:
        if force:
            force_used = True
        else:
            raise CheckInError(
                _('This ticket has been blocked.'),  # todo provide reason
                'blocked'
            )

    if type != Checkin.TYPE_EXIT and op.valid_from and op.valid_from > dt:
        if force:
            force_used = True
        else:
            raise CheckInError(
                _('This ticket is only valid after {datetime}.').format(
                    datetime=date_format(op.valid_from.astimezone(clist.event.timezone), 'SHORT_DATETIME_FORMAT')
                ),
                'invalid_time',
                _('This ticket is only valid after {datetime}.').format(
                    datetime=date_format(op.valid_from.astimezone(clist.event.timezone), 'SHORT_DATETIME_FORMAT')
                ),
            )

    if type != Checkin.TYPE_EXIT and op.valid_until and op.valid_until < dt:
        if force:
            force_used = True
        else:
            raise CheckInError(
                _('This ticket was only valid before {datetime}.').format(
                    datetime=date_format(op.valid_until.astimezone(clist.event.timezone), 'SHORT_DATETIME_FORMAT')
                ),
                'invalid_time',
                _('This ticket was only valid before {datetime}.').format(
                    datetime=date_format(op.valid_until.astimezone(clist.event.timezone), 'SHORT_DATETIME_FORMAT')
                ),
            )

    # Do this outside of transaction so it is saved even if the checkin fails for some other reason
    checkin_questions = list(
        clist.event.questions.filter(ask_during_checkin=True, items__in=[op.item_id])
    )
    require_answers = []
    if type != Checkin.TYPE_EXIT and checkin_questions:
        answers = {a.question: a for a in op.answers.all()}
        for q in checkin_questions:
            if q not in given_answers and q not in answers:
                require_answers.append(q)

        if not simulate:
            _save_answers(op, answers, given_answers)

    with transaction.atomic():
        # Lock order positions, if it is an entry. We don't need it for exits, as a race condition wouldn't be problematic
        opqs = OrderPosition.all
        if type != Checkin.TYPE_EXIT:
            opqs = opqs.select_for_update(of=OF_SELF)
        op = opqs.get(pk=op.pk)

        if not clist.all_products and op.item_id not in [i.pk for i in clist.limit_products.all()]:
            if force:
                force_used = True
            else:
                raise CheckInError(
                    _('This order position has an invalid product for this check-in list.'),
                    'product'
                )

        if clist.subevent_id and op.subevent_id != clist.subevent_id:
            if force:
                force_used = True
            else:
                raise CheckInError(
                    _('This order position has an invalid date for this check-in list.'),
                    'product'
                )

        if op.order.status != Order.STATUS_PAID and op.order.require_approval:
            if force:
                force_used = True
            else:
                raise CheckInError(
                    _('This order is not yet approved.'),
                    'unpaid'
                )
        elif op.order.status != Order.STATUS_PAID and not op.order.valid_if_pending and not (
            ignore_unpaid and clist.include_pending and op.order.status == Order.STATUS_PENDING
        ):
            if force:
                force_used = True
            else:
                raise CheckInError(
                    _('This order is not marked as paid.'),
                    'unpaid'
                )

        if type == Checkin.TYPE_ENTRY and clist.rules:
            rule_data = LazyRuleVars(op, clist, dt)
            logic = _get_logic_environment(op.subevent or clist.event, now_dt=dt)
            if not logic.apply(clist.rules, rule_data):
                if force:
                    force_used = True
                else:
                    reason = _logic_explain(clist.rules, op.subevent or clist.event, rule_data)
                    raise CheckInError(
                        _('Entry not permitted: {explanation}.').format(
                            explanation=reason
                        ),
                        'rules',
                        reason=reason
                    )

        if require_answers and not force and questions_supported:
            raise RequiredQuestionsError(
                _('You need to answer questions to complete this check-in.'),
                'incomplete',
                require_answers
            )

        device = None
        if isinstance(auth, Device):
            device = auth

        last_cis = list(op.checkins.order_by('-datetime').filter(list=clist).only('type', 'nonce'))
        entry_allowed = (
            type == Checkin.TYPE_EXIT or
            clist.allow_multiple_entries or
            not last_cis or
            all(c.type == Checkin.TYPE_EXIT for c in last_cis) or
            (clist.allow_entry_after_exit and last_cis[0].type == Checkin.TYPE_EXIT)
        )

        if nonce and ((last_cis and last_cis[0].nonce == nonce) or op.checkins.filter(type=type, list=clist, device=device, nonce=nonce).exists()):
            return

        if entry_allowed or force:
            if simulate:
                return True
            else:
                ci = Checkin.objects.create(
                    position=op,
                    type=type,
                    list=clist,
                    datetime=dt,
                    device=device,
                    gate=device.gate if device else None,
                    nonce=nonce,
                    forced=force and (not entry_allowed or from_revoked_secret or force_used),
                    force_sent=force,
                    raw_barcode=raw_barcode,
                    raw_source_type=raw_source_type,
                )
                op.order.log_action('pretix.event.checkin', data={
                    'position': op.id,
                    'positionid': op.positionid,
                    'first': True,
                    'forced': force or op.order.status != Order.STATUS_PAID,
                    'datetime': dt,
                    'type': type,
                    'answers': {k.pk: str(v) for k, v in given_answers.items()},
                    'list': clist.pk
                }, user=user, auth=auth)
                checkin_created.send(op.order.event, checkin=ci)
        else:
            raise CheckInError(
                _('This ticket has already been redeemed.'),
                'already_redeemed',
            )


@receiver(order_placed, dispatch_uid="autocheckin_order_placed")
def order_placed(sender, **kwargs):
    order = kwargs['order']
    event = sender

    cls = list(event.checkin_lists.filter(auto_checkin_sales_channels__contains=order.sales_channel).prefetch_related(
        'limit_products'))
    if not cls:
        return
    for op in order.positions.all():
        for cl in cls:
            if cl.all_products or op.item_id in {i.pk for i in cl.limit_products.all()}:
                if not cl.subevent_id or cl.subevent_id == op.subevent_id:
                    ci = Checkin.objects.create(position=op, list=cl, auto_checked_in=True, type=Checkin.TYPE_ENTRY)
                    checkin_created.send(event, checkin=ci)


@receiver(periodic_task, dispatch_uid="autocheckin_exit_all")
@scopes_disabled()
def process_exit_all(sender, **kwargs):
    qs = CheckinList.objects.filter(
        exit_all_at__lte=now(),
        exit_all_at__isnull=False
    ).select_related('event', 'event__organizer')
    for cl in qs:
        positions = cl.positions_inside_query(ignore_status=True, at_time=cl.exit_all_at)
        for p in positions:
            with scope(organizer=cl.event.organizer):
                ci = Checkin.objects.create(
                    position=p, list=cl, auto_checked_in=True, type=Checkin.TYPE_EXIT, datetime=cl.exit_all_at
                )
                checkin_created.send(cl.event, checkin=ci)
        d = cl.exit_all_at.astimezone(cl.event.timezone)
        if cl.event.settings.get(f'autocheckin_dst_hack_{cl.pk}'):  # move time back if yesterday was DST switch
            d -= timedelta(hours=1)
            cl.event.settings.delete(f'autocheckin_dst_hack_{cl.pk}')

        cl.exit_all_at = make_aware(datetime.combine(d.date() + timedelta(days=1), d.time().replace(fold=1)), cl.event.timezone)
        if not datetime_exists(cl.exit_all_at):
            cl.event.settings.set(f'autocheckin_dst_hack_{cl.pk}', True)
            d += timedelta(hours=1)
            cl.exit_all_at = make_aware(datetime.combine(d.date() + timedelta(days=1), d.time().replace(fold=1)), cl.event.timezone)
            # AmbiguousTimeError shouldn't be possible since d.time() includes fold=0
        cl.save(update_fields=['exit_all_at'])
