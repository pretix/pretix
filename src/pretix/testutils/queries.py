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
from django.db import DEFAULT_DB_ALIAS, connections
from django.test.utils import CaptureQueriesContext


class _AssertNumQueriesContext(CaptureQueriesContext):
    # Inspired by /django/test/testcases.py
    # but copied over to work without the unit test module
    def __init__(self, num, connection):
        self.num = num
        super(_AssertNumQueriesContext, self).__init__(connection)

    def __exit__(self, exc_type, exc_value, traceback):
        super(_AssertNumQueriesContext, self).__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return
        executed = len(self)
        assert executed == self.num, "%d queries executed, %d expected\nCaptured queries were:\n%s" % (
            executed, self.num,
            '\n'.join(
                query['sql'] for query in self.captured_queries
            )
        )


def assert_num_queries(num, func=None, *args, **kwargs):
    using = kwargs.pop("using", DEFAULT_DB_ALIAS)
    conn = connections[using]

    context = _AssertNumQueriesContext(num, conn)
    if func is None:
        return context

    with context:
        func(*args, **kwargs)
