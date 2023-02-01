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
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django_scopes import scopes_disabled
from freezegun import freeze_time

tz = ZoneInfo("Asia/Tokyo")


@pytest.mark.django_db
def test_no_events(device_client, device):
    resp = device_client.get('/api/v1/device/eventselection?current_event=e1')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_choose_between_events(device_client, device):
    with scopes_disabled():
        e1 = device.organizer.events.create(
            name="Event", slug="e1", live=True,
            date_from=datetime(2020, 1, 10, 14, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 15, 0, tzinfo=tz),
        )
        cl1 = e1.checkin_lists.create(name="Same name")
        e2 = device.organizer.events.create(
            name="Event", slug="e2", live=True,
            date_from=datetime(2020, 1, 10, 16, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 17, 0, tzinfo=tz),
        )
        e2.checkin_lists.create(name="Other name")
        cl2 = e2.checkin_lists.create(name="Same name")
        e2.checkin_lists.create(name="Yet another name")
        tomorrow = device.organizer.events.create(
            name="Event", slug="tomorrow", live=True,
            date_from=datetime(2020, 1, 11, 15, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 11, 16, 0, tzinfo=tz),
        )
        cl3 = tomorrow.checkin_lists.create(name="Just any name")
        for e in device.organizer.events.all():
            e.settings.timezone = "Asia/Tokyo"

    # Keep current when still running
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 304
    with freeze_time("2020-01-10T16:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection?current_event=e1')
        assert resp.status_code == 200
        resp = device_client.get('/api/v1/device/eventselection?current_event=e2')
        assert resp.status_code == 304

    # Next one only
    with freeze_time("2020-01-10T12:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'

    # Last one only
    with freeze_time("2020-01-10T17:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e2'

    # Running one
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
    with freeze_time("2020-01-10T16:01:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e2'
        assert resp.data['checkinlist'] == cl2.pk

    # Prefer the one on the same day
    with freeze_time("2020-01-10T23:59:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e2'
        assert resp.data['checkinlist'] == cl2.pk
    with freeze_time("2020-01-11T01:00:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'tomorrow'
        assert resp.data['checkinlist'] == cl3.pk

    # Switch at half-time
    with freeze_time("2020-01-10T15:29:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
    with freeze_time("2020-01-10T15:31:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e2'

    # check for overlapping events
    e2.date_admission = datetime(2020, 1, 10, 14, 45, tzinfo=tz)
    e2.save()
    with freeze_time("2020-01-10T14:45:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection?current_event=e1')
        assert resp.status_code == 200
        resp = device_client.get('/api/v1/device/eventselection?current_event=e2')
        assert resp.status_code == 304


@pytest.mark.django_db
def test_choose_between_subevents(device_client, device):
    with scopes_disabled():
        e = device.organizer.events.create(
            name="Event", slug="e1", live=True,
            date_from=datetime(2020, 1, 10, 14, 0, tzinfo=tz),
            has_subevents=True,
        )
        e.settings.timezone = "Asia/Tokyo"
        se1 = e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 10, 14, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 15, 0, tzinfo=tz),
        )
        cl1 = e.checkin_lists.create(name="Same name", subevent=se1)
        se2 = e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 10, 16, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 17, 0, tzinfo=tz),
        )
        cl2 = e.checkin_lists.create(name="Same name", subevent=se2)
        cl3 = e.checkin_lists.create(name="Other name")
        e.checkin_lists.create(name="Yet another name", subevent=se2)
        se_tomorrow = e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 11, 15, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 11, 16, 0, tzinfo=tz),
        )
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_subevent={se1.pk}')
        assert resp.status_code == 304
    with freeze_time("2020-01-10T16:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_subevent={se1.pk}')
        assert resp.status_code == 200
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_subevent={se2.pk}')
        assert resp.status_code == 304

    # Next one only
    with freeze_time("2020-01-10T12:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se1.pk

    # Last one only
    with freeze_time("2020-01-10T17:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se2.pk

    # Running one
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se1.pk
    with freeze_time("2020-01-10T16:01:00+09:00"):
        resp = device_client.get(
            f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}&current_subevent={se1.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se2.pk
        assert resp.data['checkinlist'] == cl2.pk

    # Prefer the one on the same day
    with freeze_time("2020-01-10T23:59:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se2.pk
    with freeze_time("2020-01-11T01:00:00+09:00"):
        resp = device_client.get(
            f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}&current_subevent={se1.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se_tomorrow.pk
        assert resp.data['checkinlist'] == cl3.pk

    # Switch at half-time
    with freeze_time("2020-01-10T15:29:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se1.pk
    with freeze_time("2020-01-10T15:31:00+09:00"):
        resp = device_client.get('/api/v1/device/eventselection')
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se2.pk

    # check for overlapping events
    se2.date_admission = datetime(2020, 1, 10, 14, 45, tzinfo=tz)
    se2.save()
    with freeze_time("2020-01-10T14:45:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_subevent={se1.pk}')
        assert resp.status_code == 200
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_subevent={se2.pk}')
        assert resp.status_code == 304


@pytest.mark.django_db
def test_require_gate(device_client, device):
    with scopes_disabled():
        g = device.organizer.gates.create(name="Gate 1")
        device.gate = g
        device.save()
        e = device.organizer.events.create(
            name="Event", slug="e1", live=True,
            date_from=datetime(2020, 1, 10, 14, 0, tzinfo=tz),
            has_subevents=True,
        )
        e.settings.timezone = "Asia/Tokyo"
        se0 = e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 10, 9, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 10, 0, tzinfo=tz),
        )
        e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 10, 14, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 15, 0, tzinfo=tz),
        )
        cl1 = e.checkin_lists.create(name="Same name", subevent=se0)
        se2 = e.subevents.create(
            name="Event", active=True,
            date_from=datetime(2020, 1, 10, 16, 0, tzinfo=tz),
            date_to=datetime(2020, 1, 10, 17, 0, tzinfo=tz),
        )
        e.checkin_lists.create(name="Same name", subevent=se2)
        cl3 = e.checkin_lists.create(name="Other name", subevent=se2)
        cl3.gates.add(g)

    with freeze_time("2020-01-10T11:00:00+09:00"):
        resp = device_client.get(
            f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}&current_subevent={se0.pk}')
        assert resp.status_code == 200
        assert resp.data['event']['slug'] == 'e1'
        assert resp.data['subevent'] == se2.pk
        assert resp.data['checkinlist'] == cl3.pk
