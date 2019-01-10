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
