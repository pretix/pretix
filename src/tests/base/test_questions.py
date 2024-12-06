from pretix.base.forms.questions import name_parts_is_empty


def test_name_parts_is_empty():
    assert name_parts_is_empty({}) is True
    assert name_parts_is_empty({"_scheme": "foo"}) is True
    assert name_parts_is_empty({"_scheme": "foo", "full_name": ""}) is True
    assert name_parts_is_empty({"full_name": None}) is True
    assert name_parts_is_empty({"full_name": "Flora Nord"}) is False
    assert name_parts_is_empty({"_scheme": "foo", "given_name": "Alice"}) is False
    assert name_parts_is_empty({"_legacy": "Alice"}) is False
