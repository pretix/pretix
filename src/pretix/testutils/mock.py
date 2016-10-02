from contextlib import contextmanager

from pytest_mock import MockFixture


@contextmanager
def mocker_context():
    result = MockFixture()
    yield result
    result.stopall()
