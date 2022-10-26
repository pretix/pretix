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
import inspect

import pytest
from django_scopes import scopes_disabled
from xdist.dsession import DSession

CRASHED_ITEMS = set()


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """
    Somehow, somewhere, our test suite causes a segfault in SQLite, but only when run
    on Travis CI in full. Therefore, we monkeypatch pytest-xdist to retry segfaulted
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
