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
from contextlib import contextmanager

import fakeredis
from pytest_mock import MockFixture


class FakePytestConfig:
    def getini(self, *args, **kwargs):
        return 'False'


@contextmanager
def mocker_context():
    result = MockFixture(FakePytestConfig())
    yield result
    result.stopall()


def get_redis_connection(alias="default", write=True):
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id and worker_id.startswith("gw"):
        redis_port = 1000 + int(worker_id.replace("gw", ""))
    else:
        redis_port = 1000
    return fakeredis.FakeStrictRedis(server=fakeredis.FakeServer.get_server(f"127.0.0.1:{redis_port}:redis:v(7, 0)", (7, 0), server_type="redis"))
