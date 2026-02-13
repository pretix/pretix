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
from pretix.helpers.format import (
    PlainHtmlAlternativeString, SafeFormatter, format_map,
)


def test_format_map():
    assert format_map("Foo {bar}", {"bar": 3}) == "Foo 3"
    assert format_map("Foo {baz}", {"bar": 3}) == "Foo {baz}"
    assert format_map("Foo {bar.__module__}", {"bar": 3}) == "Foo {bar.__module__}"
    assert format_map("Foo {bar!s}", {"bar": 3}) == "Foo 3"
    assert format_map("Foo {bar!r}", {"bar": '3'}) == "Foo 3"
    assert format_map("Foo {bar!a}", {"bar": '3'}) == "Foo 3"
    assert format_map("Foo {bar:<20}", {"bar": 3}) == "Foo 3"


def test_format_alternatives():
    ctx = {
        "bar": PlainHtmlAlternativeString(
            "plain text",
            "<span>HTML version</span>",
        )
    }

    assert format_map("Foo {bar}", ctx, mode=SafeFormatter.MODE_RICH_TO_PLAIN) == "Foo plain text"
    assert format_map("Foo {bar}", ctx, mode=SafeFormatter.MODE_RICH_TO_HTML) == "Foo <span>HTML version</span>"
