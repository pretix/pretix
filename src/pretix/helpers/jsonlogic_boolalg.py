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
import logging

logger = logging.getLogger(__name__)


def convert_to_dnf(rules):
    """
    Converts a set of rules to disjunctive normal form, i.e. returns something of the form
    `(a AND b AND c) OR (a AND d AND f)`
    without further nesting.
    """
    if not isinstance(rules, dict):
        return rules

    def _distribute_or_over_and(r):
        operator = list(r.keys())[0]
        values = r[operator]
        if operator == "and":
            arg_to_distribute = [arg for arg in values if isinstance(arg, dict) and "or" in arg]
            if not arg_to_distribute:
                return rules
            arg_to_distribute = arg_to_distribute[0]
            other_args = [arg for arg in values if arg is not arg_to_distribute]
            return {
                "or": [
                    {"and": [*other_args, dval]} for dval in arg_to_distribute["or"]
                ]
            }
        elif operator in ("!", "!!", "?:", "if"):
            raise ValueError(f"Operator {operator} currently unsupported by convert_to_dnf")
        else:
            return r

    def _simplify_chained_operators(r):
        # Simplify `(a OR b) OR (c or d)` to `a OR b OR c OR d` and the same with `AND`
        if not isinstance(r, dict):
            return r
        operator = list(r.keys())[0]
        values = r[operator]
        if operator not in ("or", "and"):
            return r
        new_values = []
        for v in values:
            if not isinstance(v, dict) or operator not in v:
                new_values.append(v)
            else:
                new_values += v[operator]
        return {operator: new_values}

    # Run _distribute_or_over_and on until it no longer changes anything. Do so recursively
    # for the full expression tree.
    old_rules = rules
    while True:
        rules = _distribute_or_over_and(rules)
        operator = list(rules.keys())[0]
        values = rules[operator]
        no_list = False
        if not isinstance(values, list):
            values = [values]
            no_list = True
        rules = {
            operator: [
                convert_to_dnf(v) for v in values
            ] if not no_list else convert_to_dnf(values[0])
        }
        if old_rules == rules:
            break
        old_rules = rules
    # Simplify leftovers of the recursion
    rules = _simplify_chained_operators(rules)
    return rules
