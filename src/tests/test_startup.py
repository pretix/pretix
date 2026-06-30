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
import os
import subprocess
import sys
import tempfile


def test_start_with_redis_down():
    """
    This is a test that ensures that pretix is able to start without a running redis server,
    even if one is configured.
    """
    with tempfile.NamedTemporaryFile(suffix="cfg") as f:
        f.write(b"[redis]\nlocation=redis://127.0.0.99:65534/2\n")
        f.flush()

        assert subprocess.check_call(
            [
                sys.executable,
                os.path.join(os.path.dirname(__file__), '../manage.py'),
                "noop",
            ],
            env={
                "PRETIX_CONFIG_FILE": f.name,
            }
        ) == 0
