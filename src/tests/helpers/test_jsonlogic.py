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
import json
import os

import pytest

from pretix.helpers.jsonlogic import Logic

with open(os.path.join(os.path.dirname(__file__), 'jsonlogic-tests.json'), 'r') as f:
    data = json.load(f)
    params = [r for r in data if isinstance(r, list)]

params += [
    ({"==": [True, True]}, {}, True),
    ({"==": [True, False]}, {}, False),
    ({"<": [0, "foo"]}, {}, False),
    ({"+": [3.4, "0.1"]}, {}, 3.5),
    ({"missing_some": [0, {'var': ''}]}, {}, []),
]


@pytest.mark.parametrize("logic,data,expected", params)
def test_shared_tests(logic, data, expected):
    assert Logic().apply(logic, data) == expected


def test_unknown_operator():
    with pytest.raises(ValueError):
        assert Logic().apply({'unknownOp': []}, {})


def test_custom_operation():
    logic = Logic()
    logic.add_operation('double', lambda a: a * 2)
    assert logic.apply({'double': [{'var': 'value'}]}, {'value': 3}) == 6
