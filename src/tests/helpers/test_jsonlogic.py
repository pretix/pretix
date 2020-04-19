import json
import os

import pytest

from pretix.helpers.jsonlogic import json_logic

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
    assert json_logic(logic, data) == expected


def test_unknown_operator():
    with pytest.raises(ValueError):
        assert json_logic({'unknownOp': []}, {})
