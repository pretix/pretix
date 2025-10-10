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
import inspect
import os

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import translation
from django_scopes import scopes_disabled
from fakeredis import FakeConnection
from xdist.dsession import DSession

from pretix.testutils.mock import get_redis_connection

CRASHED_ITEMS = set()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """
    Somehow, somewhere, our test suite causes a segfault in SQLite in the past, but only when run
    on CI in full. Therefore, we monkeypatch pytest-xdist to retry segfaulted
    tests and keep fingers crossed that this doesn't turn into an infinite loop.
    """

    def _handle_crashitem(self, nodeid, worker):
        first = nodeid not in CRASHED_ITEMS
        runner = self.config.pluginmanager.getplugin("runner")
        fspath = nodeid.split("::")[0]
        msg = "Worker %r crashed while running %r" % (worker.gateway.id, nodeid)
        CRASHED_ITEMS.add(nodeid)
        rep = runner.TestReport(
            nodeid, (fspath, None, fspath), (), "restarted" if first else "failed", msg, "???"
        )
        rep.node = worker
        self.config.hook.pytest_runtest_logreport(report=rep)

        # Schedule retry
        if first:
            self.sched.pending.append(self.sched.collection.index(nodeid))
            for node in self.sched.node2pending:
                self.sched.check_schedule(node)

    DSession.handle_crashitem = _handle_crashitem


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    """
    This hack automatically disables django-scopes for all fixtures which are not yield fixtures.
    This saves us a *lot* of decorcators…
    """
    if inspect.isgeneratorfunction(fixturedef.func):
        yield
    else:
        with scopes_disabled():
            yield


@pytest.fixture(autouse=True)
def reset_locale():
    translation.activate("en")


@pytest.fixture
def fakeredis_client(monkeypatch):
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id and worker_id.startswith("gw"):
        redis_port = 1000 + int(worker_id.replace("gw", ""))
    else:
        redis_port = 1000
    with override_settings(
        HAS_REDIS=True,
        REAL_CACHE_USED=True,
        CACHES={
            'redis': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': f'redis://127.0.0.1:{redis_port}',
                'OPTIONS': {
                    'connection_class': FakeConnection
                }
            },
            'redis_session': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': f'redis://127.0.0.1:{redis_port}',
                'OPTIONS': {
                    'connection_class': FakeConnection
                }
            },
            'default': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': f'redis://127.0.0.1:{redis_port}',
                'OPTIONS': {
                    'connection_class': FakeConnection
                }
            },
        }
    ):
        cache.clear()
        redis = get_redis_connection("default", True)
        redis.flushall()
        monkeypatch.setattr('django_redis.get_redis_connection', get_redis_connection, raising=False)
        yield redis


@pytest.fixture(autouse=True)
def set_lock_namespaces(request):
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id and worker_id.startswith("gw"):
        with override_settings(DATABASE_ADVISORY_LOCK_INDEX=int(worker_id.replace("gw", ""))):
            yield
    else:
        yield
