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

import pytest
from django.conf import settings
from django.test import override_settings
from django_scopes import scope, scopes_disabled

from pretix.base.models import Organizer
from pretix.base.models.orders import Order, OrderPayment
from pretix.helpers import OF_SELF, UnsafeSQLQueryException


@pytest.fixture
def pg_only():
    if 'postgres' not in settings.DATABASES['default']['ENGINE']:
        pytest.skip("Test only runs on PostgreSQL")


@pytest.fixture
def organizer():
    return Organizer.objects.create(name="Dummy", slug="dummy")


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_fail_on_debug(pg_only, organizer):
    with scope(organizer=organizer):
        with pytest.raises(UnsafeSQLQueryException):
            list(OrderPayment.objects.select_for_update())  # join added by django-scopes
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.select_related("event").select_for_update())
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update())
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update(no_key=True))
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update(nowait=True))
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update(skip_locked=True))
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update(nowait=True, no_key=True))
        with pytest.raises(UnsafeSQLQueryException):
            list(Order.objects.filter(event__slug="test").select_for_update(skip_locked=True, no_key=True))


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ok_with_of(pg_only, organizer):
    with scope(organizer=organizer):
        list(OrderPayment.objects.select_for_update(of=OF_SELF))  # join added by django-scopes
        list(Order.objects.select_related("event").select_for_update(of=OF_SELF))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF, no_key=True))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF, nowait=True))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF, skip_locked=True))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF, nowait=True, no_key=True))
        list(Order.objects.filter(event__slug="test").select_for_update(of=OF_SELF, skip_locked=True, no_key=True))


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ok_without_join(pg_only, organizer):
    with scope(organizer=organizer):
        assert list(Order.objects.select_for_update()) == []
    with scopes_disabled():
        assert list(OrderPayment.objects.select_for_update()) == []


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_fail_silently_without_debug(pg_only, organizer):
    with scope(organizer=organizer):
        list(OrderPayment.objects.select_for_update())  # join added by django-scopes
        list(Order.objects.select_related("event").select_for_update())
