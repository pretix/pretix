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
from pretix.base.datasync.datasync import MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW, MODE_APPEND_LIST
from pretix.base.datasync.utils import assign_properties


def test_assign_properties():
    assert assign_properties(
        [("name", "Alice", MODE_OVERWRITE)], {"name": "A"}, is_new=False
    ) == {"name": "Alice"}
    assert (
        assign_properties([("name", "Alice", MODE_SET_IF_NEW)], {}, is_new=False) == {}
    )
    assert assign_properties([("name", "Alice", MODE_SET_IF_NEW)], {}, is_new=True) == {
        "name": "Alice"
    }
    assert assign_properties(
        [
            ("name", "Alice", MODE_SET_IF_NEW),
            ("name", "A", MODE_SET_IF_NEW),
        ],
        {},
        is_new=True,
    ) == {"name": "Alice"}
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_NEW),
                ("name", "A", MODE_SET_IF_NEW),
            ],
            {"name": "Bob"},
            is_new=False,
        )
        == {}
    )
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_NEW),
                ("name", "A", MODE_SET_IF_NEW),
            ],
            {},
            is_new=False,
        )
        == {}
    )
    assert assign_properties(
        [
            ("name", "Alice", MODE_SET_IF_EMPTY),
            ("name", "A", MODE_SET_IF_EMPTY),
        ],
        {},
        is_new=True,
    ) == {"name": "Alice"}
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_EMPTY),
                ("name", "A", MODE_SET_IF_EMPTY),
            ],
            {"name": "Bob"},
            is_new=False,
        )
        == {}
    )
    assert assign_properties(
        [("name", "Alice", MODE_SET_IF_EMPTY)], {}, is_new=False
    ) == {"name": "Alice"}

    assert assign_properties(
        [("name", "Alice", MODE_SET_IF_EMPTY)], {}, is_new=False
    ) == {"name": "Alice"}

    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {}, is_new=False
    ) == {"colors": "red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "red"}, is_new=False
    ) == {"colors": "red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "blue"}, is_new=False
    ) == {"colors": "blue;red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "green;blue"}, is_new=False
    ) == {"colors": "green;blue;red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": ["green","blue"]}, is_new=False, list_sep=None
    ) == {"colors": ["green", "blue", "red"]}
    assert assign_properties(
        [("colors", "green", MODE_APPEND_LIST)], {"colors": ["green","blue"]}, is_new=False, list_sep=None
    ) == {"colors": ["green", "blue"]}
