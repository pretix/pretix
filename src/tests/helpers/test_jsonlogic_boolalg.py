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

import pytest

from pretix.helpers.jsonlogic_boolalg import convert_to_dnf

params = [
    (
        {"and": [{"var": "a"}, {"eq": [{"var": "a"}, 3]}]},
        {"and": [{"var": "a"}, {"eq": [{"var": "a"}, 3]}]},
    ),
    (
        {"or": [{"var": "a"}, {"eq": [{"var": "a"}, 3]}]},
        {"or": [{"var": "a"}, {"eq": [{"var": "a"}, 3]}]},
    ),
    (
        {"and": [{"or": ["a", "b"]}, 3]},
        {"or": [{"and": [3, "a"]}, {"and": [3, "b"]}]},
    ),
    (
        {"and": [{"or": ["a", "b"]}, {"or": ["c", "d"]}]},
        {"or": [{"and": ["a", "c"]}, {"and": ["a", "d"]}, {"and": ["b", "c"]}, {"and": ["b", "d"]}]},
    ),
    (
        {"and": [{"or": ["a", {"and": ["e", "f"]}]}, {"or": ["c", "d"]}]},
        {"or": [{"and": ["a", "c"]}, {"and": ["a", "d"]}, {"and": ["e", "f", "c"]}, {"and": ["e", "f", "d"]}]},
    ),
    (
        {"and": [{"or": ["a", {"and": ["e", {"or": ["f", "g"]}]}]}, {"or": ["c", "d"]}]},
        {"or": [{"and": ["a", "c"]}, {"and": ["a", "d"]}, {"and": ["c", "e", "f"]}, {"and": ["c", "e", "g"]},
                {"and": ["d", "e", "f"]}, {"and": ["d", "e", "g"]}]},
    ),
    (
        {"and": [{"or": ["a", {"and": ["e", {"or": ["f", {"and": ["g", "h"]}]}]}]}, {"or": ["c", "d"]}]},
        {"or": [{"and": ["a", "c"]}, {"and": ["a", "d"]}, {"and": ["c", "e", "f"]}, {"and": ["c", "e", "g", "h"]},
                {"and": ["d", "e", "f"]}, {"and": ["d", "e", "g", "h"]}]},
    ),
]


def compare_ignoring_order(data1, data2):
    if isinstance(data1, list) and isinstance(data2, list):
        try:
            assert set(data1) == set(data2)
        except:
            assert len(data1) == len(data2) and all(data1.count(i) == data2.count(i) for i in data1)
    elif isinstance(data1, dict) and isinstance(data2, dict):
        assert set(data1.keys()) == set(data2.keys())
        compare_ignoring_order(list(data1.values()), list(data2.values()))
    else:
        assert data1 == data2


@pytest.mark.parametrize("logic,expected", params)
def test_convert_to_dnf(logic, expected):
    assert convert_to_dnf(logic) == expected
