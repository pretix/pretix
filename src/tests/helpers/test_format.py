from pretix.helpers.format import format_map


def test_format_map():
    assert format_map("Foo {bar}", {"bar": 3}) == "Foo 3"
    assert format_map("Foo {baz}", {"bar": 3}) == "Foo {baz}"
    assert format_map("Foo {bar.__module__}", {"bar": 3}) == "Foo {bar.__module__}"
    assert format_map("Foo {bar!s}", {"bar": 3}) == "Foo 3"
    assert format_map("Foo {bar:<20}", {"bar": 3}) == "Foo 3"
