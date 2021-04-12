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
import time

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.models import Event, Organizer
from pretix.base.services import locking
from pretix.base.services.locking import (
    LockReleaseException, LockTimeoutException,
)


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    with scope(organizer=o):
        yield event


@pytest.mark.django_db
def test_locking_exclusive(event):
    with event.lock():
        with pytest.raises(LockTimeoutException):
            with scopes_disabled():
                ev = Event.objects.get(id=event.id)
                with ev.lock():
                    pass


@pytest.mark.django_db
def test_locking_different_events(event):
    other = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=now()
    )
    with event.lock():
        with other.lock():
            pass


@pytest.mark.django_db
def test_lock_timeout_steal(event):
    locking.LOCK_TIMEOUT = 1
    locking.lock_event(event)
    with pytest.raises(LockTimeoutException):
        ev = Event.objects.get(id=event.id)
        locking.lock_event(ev)
    time.sleep(1.5)
    locking.lock_event(ev)
    with pytest.raises(LockReleaseException):
        locking.release_event(event)
