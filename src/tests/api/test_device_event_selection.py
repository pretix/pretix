from datetime import datetime

import pytest
import pytz
from django_scopes import scopes_disabled
from freezegun import freeze_time

tz = pytz.timezone("Asia/Tokyo")


@pytest.mark.django_db
def test_no_events(device_client, device):
    resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_choose_between_events(device_client, device):
    with scopes_disabled():
        e1 = device.organizer.events.create(
            name="Event", slug="e1", live=True,
            date_from=tz.localize(datetime(2020, 1, 10, 14, 0)),
            date_to=tz.localize(datetime(2020, 1, 10, 15, 0)),
        )
        cl1 = e1.checkin_lists.create(name="Same name")
        e2 = device.organizer.events.create(
            name="Event", slug="e2", live=True,
            date_from=tz.localize(datetime(2020, 1, 10, 16, 0)),
            date_to=tz.localize(datetime(2020, 1, 10, 17, 0)),
        )
        e2.checkin_lists.create(name="Other name")
        cl2 = e2.checkin_lists.create(name="Same name")
        e2.checkin_lists.create(name="Yet another name")
        tomorrow = device.organizer.events.create(
            name="Event", slug="tomorrow", live=True,
            date_from=tz.localize(datetime(2020, 1, 11, 15, 0)),
            date_to=tz.localize(datetime(2020, 1, 11, 16, 0)),
        )
        cl3 = tomorrow.checkin_lists.create(name="Just any name")
        for e in device.organizer.events.all():
            e.settings.timezone = "Asia/Tokyo"

    # Keep current when still running
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 304
    with freeze_time("2020-01-10T16:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1')
        assert resp.status_code == 200
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e2')
        assert resp.status_code == 304

    # Next one only
    with freeze_time("2020-01-10T12:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'

    # Last one only
    with freeze_time("2020-01-10T17:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e2'

    # Running one
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
    with freeze_time("2020-01-10T16:01:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e2'
        assert resp.data['checkinlist'] == cl2.pk

    # Prefer the one on the same day
    with freeze_time("2020-01-10T23:59:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e2'
        assert resp.data['checkinlist'] == cl2.pk
    with freeze_time("2020-01-11T01:00:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}')
        assert resp.status_code == 200
        assert resp.data['event'] == 'tomorrow'
        assert resp.data['checkinlist'] == cl3.pk

    # Switch at half-time
    with freeze_time("2020-01-10T15:29:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
    with freeze_time("2020-01-10T15:31:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e2'


@pytest.mark.django_db
def test_choose_between_subevents(device_client, device):
    with scopes_disabled():
        e = device.organizer.events.create(
            name="Event", slug="e1", live=True,
            date_from=tz.localize(datetime(2020, 1, 10, 14, 0)),
            has_subevents=True,
        )
        e.settings.timezone = "Asia/Tokyo"
        se1 = e.subevents.create(
            name="Event", active=True,
            date_from=tz.localize(datetime(2020, 1, 10, 14, 0)),
            date_to=tz.localize(datetime(2020, 1, 10, 15, 0)),
        )
        cl1 = e.checkin_lists.create(name="Same name", subevent=se1)
        se2 = e.subevents.create(
            name="Event", active=True,
            date_from=tz.localize(datetime(2020, 1, 10, 16, 0)),
            date_to=tz.localize(datetime(2020, 1, 10, 17, 0)),
        )
        cl2 = e.checkin_lists.create(name="Same name", subevent=se2)
        cl3 = e.checkin_lists.create(name="Other name")
        e.checkin_lists.create(name="Yet another name", subevent=se2)
        se_tomorrow = e.subevents.create(
            name="Event", active=True,
            date_from=tz.localize(datetime(2020, 1, 11, 15, 0)),
            date_to=tz.localize(datetime(2020, 1, 11, 16, 0)),
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
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se1.pk

    # Last one only
    with freeze_time("2020-01-10T17:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se2.pk

    # Running one
    with freeze_time("2020-01-10T14:30:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se1.pk
    with freeze_time("2020-01-10T16:01:00+09:00"):
        resp = device_client.get(
            f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}&current_subevent={se1.pk}')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se2.pk
        assert resp.data['checkinlist'] == cl2.pk

    # Prefer the one on the same day
    with freeze_time("2020-01-10T23:59:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se2.pk
    with freeze_time("2020-01-11T01:00:00+09:00"):
        resp = device_client.get(
            f'/api/v1/device/eventselection?current_event=e1&current_checkinlist={cl1.pk}&current_subevent={se1.pk}')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se_tomorrow.pk
        assert resp.data['checkinlist'] == cl3.pk

    # Switch at half-time
    with freeze_time("2020-01-10T15:29:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.status_code == 200
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se1.pk
    with freeze_time("2020-01-10T15:31:00+09:00"):
        resp = device_client.get(f'/api/v1/device/eventselection')
        assert resp.data['event'] == 'e1'
        assert resp.data['subevent'] == se2.pk
