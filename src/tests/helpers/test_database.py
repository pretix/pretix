"""
Tests for the ``ensure_no_queries`` context manager.

No mocking is used: every test runs against a real database connection via the
``django_db`` marker. ``settings.DEBUG`` is toggled through pytest-django's
``settings`` fixture, which restores the original value after each test.
"""

import logging
import os

import pytest
from django_scopes import scopes_disabled

from pretix.base.models import Event
from pretix.helpers.database import ensure_no_queries


@pytest.mark.django_db
def test_raises_runtime_error_in_debug(settings):
    settings.DEBUG = True

    with pytest.raises(RuntimeError, match="Unexpected DB query"):
        with scopes_disabled():
            with ensure_no_queries():
                Event.objects.exists()


@pytest.mark.django_db
def test_logs_error_when_not_debug(settings, caplog):
    settings.DEBUG = False
    os.environ.setdefault("ENSURE_NO_QUERIES_OVERRIDE", "true")

    with caplog.at_level(logging.ERROR):
        with scopes_disabled():
            with ensure_no_queries():
                Event.objects.exists()

    assert any(
        record.levelno == logging.ERROR
        and "Unexpected DB query" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db
def test_no_error_without_queries(settings, caplog):
    settings.DEBUG = True

    with caplog.at_level(logging.ERROR):
        with ensure_no_queries():
            result = sum(range(10))  # pure Python, no DB access

    assert result == 45
    assert "Unexpected DB query" not in caplog.text


@pytest.mark.django_db
def test_queries_allowed_after_context(settings):
    settings.DEBUG = True

    with ensure_no_queries():
        pass

    with scopes_disabled():
        assert Event.objects.count() == 0


@pytest.mark.django_db
def test_blocker_removed_even_after_exception(settings):
    settings.DEBUG = True

    with pytest.raises(RuntimeError, match="Unexpected DB query"):
        with scopes_disabled():
            with ensure_no_queries():
                Event.objects.exists()

    with scopes_disabled():
        assert Event.objects.count() == 0
