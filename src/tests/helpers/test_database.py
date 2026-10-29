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
                Event.objects.count()


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
