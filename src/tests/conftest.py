import pytest
from xdist.dsession import DSession


@pytest.mark.trylast
def pytest_configure(config):
    """
    Somehow, somewhere, our test suite causes a segfault in SQLite, but only when run
    on Travis CI in full. Therefore, we monkeypatch pytest-xdist to retry segfaulted
    tests and keep fingers crossed that this doesn't turn into an infinite loop.
    """

    def _handle_crashitem(self, nodeid, worker):
        runner = self.config.pluginmanager.getplugin("runner")
        fspath = nodeid.split("::")[0]
        msg = "Worker %r crashed while running %r" % (worker.gateway.id, nodeid)
        rep = runner.TestReport(
            nodeid, (fspath, None, fspath), (), "failed", msg, "???"
        )
        rep.node = worker
        self.config.hook.pytest_runtest_logreport(report=rep)

        # Schedule retry
        self.sched.pending.append(self.sched.collection.index(nodeid))
        for node in self.sched.node2pending:
            self.sched.check_schedule(node)

    DSession.handle_crashitem = _handle_crashitem
