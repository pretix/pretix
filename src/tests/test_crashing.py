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
import os

import pytest


@pytest.mark.skip
def test_crash():
    """
    This is a test that crashes with SIGKILL every (n+1)-th time it runs (n = 0, 1, 2, …).
    This is useful for debugging our pytest-xdist monkeypatch that we apply in conftest.py
    to deal with random test crashes on Travis CI using SQLite. Usually, this test is
    skipped to avoid causing additional crashes in real runs.
    """
    if os.path.exists('crashed.tmp'):
        assert 1
        os.remove('crashed.tmp')
    else:
        with open('crashed.tmp', 'w') as f:
            f.write('hi')
        os.kill(os.getpid(), 9)
