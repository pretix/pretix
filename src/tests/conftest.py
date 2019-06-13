import inspect

import pytest
from django_scopes import scopes_disabled
from xdist.dsession import DSession

CRASHED_ITEMS = set()


@pytest.mark.trylast
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
