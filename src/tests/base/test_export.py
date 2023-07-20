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
from datetime import datetime, time, timedelta, timezone

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope
from freezegun import freeze_time

from pretix.base.models import (
    Event, Organizer, ScheduledEventExport, ScheduledOrganizerExport, User,
)
from pretix.base.services.export import run_scheduled_exports


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=datetime(2023, 1, 19, 2, 30, 0, tzinfo=timezone.utc),
        plugins='pretix.plugins.banktransfer'
    )
    o.settings.timezone = "Europe/Berlin"
    with scope(organizer=o):
        yield event


@pytest.fixture
def team(event):
    return event.organizer.teams.create(all_events=True, can_view_orders=True)


@pytest.fixture
def user(team):
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    team.members.add(user)
    return user


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_run_sets_new_time(event, user):
    s = ScheduledEventExport(event=event, owner=user)
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run == datetime(2023, 1, 19, 2, 30, 0, tzinfo=event.timezone)


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_not_run_when_failed_5_times(event, user):
    s = ScheduledEventExport(event=event, owner=user)
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = datetime(2023, 1, 18, 2, 30, 0, tzinfo=event.timezone)
    s.error_counter = 5
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run == datetime(2023, 1, 18, 2, 30, 0, tzinfo=event.timezone)


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_fail_invalid_config(event, user):
    djmail.outbox = []
    s = ScheduledEventExport(event=event, owner=user)
    s.export_identifier = " invalid "
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Export failed"
    assert "Reason: Export type not found." in djmail.outbox[0].body
    assert djmail.outbox[0].to == [user.email]


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_fail_user_inactive(event, user):
    djmail.outbox = []
    s = ScheduledEventExport(event=event, owner=user)
    s.export_identifier = "orderlist"
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    user.is_active = False
    user.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 0  # no mails sent to inactive user


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_fail_user_no_permission(event, user, team):
    djmail.outbox = []
    s = ScheduledEventExport(event=event, owner=user)
    s.export_identifier = "orderlist"
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    team.can_view_orders = False
    team.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Export failed"
    assert "Reason: Permission denied." in djmail.outbox[0].body
    assert djmail.outbox[0].to == [user.email]


@pytest.mark.django_db(transaction=True)
@freeze_time("2023-01-18 03:00:00+01:00")
def test_event_ok(event, user, team):
    djmail.outbox = []
    s = ScheduledEventExport(event=event, owner=user)
    s.export_identifier = "orderlist"
    s.export_form_data = {"_format": "xlsx", "paid_only": False}
    s.mail_additional_recipients = "boss@example.org,boss@example.net"
    s.mail_additional_recipients_cc = "assistant@example.net"
    s.mail_additional_recipients_bcc = "archive@example.net"
    s.mail_subject = "Report 1"
    s.mail_template = "Here is the report."
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 1
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 0
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Report 1"
    assert "Here is the report." in djmail.outbox[0].body
    assert djmail.outbox[0].to == ["boss@example.org", "boss@example.net"]
    assert djmail.outbox[0].cc == ["assistant@example.net", user.email]
    assert djmail.outbox[0].bcc == ["archive@example.net"]
    assert len(djmail.outbox[0].attachments) == 1
    assert djmail.outbox[0].attachments[0][0] == "dummy_orders.xlsx"


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_run_sets_new_time(event, user):
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user, timezone="Europe/Berlin")
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run == datetime(2023, 1, 19, 2, 30, 0, tzinfo=event.timezone)


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_not_run_when_failed_5_times(event, user):
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = datetime(2023, 1, 18, 2, 30, 0, tzinfo=event.timezone)
    s.error_counter = 5
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run == datetime(2023, 1, 18, 2, 30, 0, tzinfo=event.timezone)


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_fail_invalid_config(event, user):
    djmail.outbox = []
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.export_identifier = " invalid "
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Export failed"
    assert "Reason: Export type not found." in djmail.outbox[0].body
    assert djmail.outbox[0].to == [user.email]


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_fail_user_inactive(event, user):
    djmail.outbox = []
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.export_identifier = "orderlist"
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    user.is_active = False
    user.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 0  # no mails sent to inactive user


@pytest.mark.django_db
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_fail_user_does_not_have_specific_permission(event, user, team):
    djmail.outbox = []
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.export_identifier = "customerlist"
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    team.can_manage_customers = False
    team.save()

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 1
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Export failed"
    assert "Reason: Permission denied." in djmail.outbox[0].body
    assert djmail.outbox[0].to == [user.email]


@pytest.mark.django_db(transaction=True)
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_limited_to_events(event, user, team):
    djmail.outbox = []
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.export_identifier = "eventdata"
    s.export_form_data = {"_format": "default", "all_events": True}
    s.mail_subject = "Report 1"
    s.mail_template = "Here is the report."
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 0
    s.save()

    event2 = Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=datetime(2023, 1, 19, 2, 30, 0, tzinfo=timezone.utc),
        plugins='pretix.plugins.banktransfer'
    )
    team.all_events = False
    team.save()
    team.limit_events.add(event2)

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 0
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Report 1"
    assert "Here is the report." in djmail.outbox[0].body
    assert djmail.outbox[0].to == [user.email]
    assert len(djmail.outbox[0].attachments) == 1
    assert djmail.outbox[0].attachments[0][0] == "dummy_events.csv"
    assert len(djmail.outbox[0].attachments[0][1].splitlines()) == 2


@pytest.mark.django_db(transaction=True)
@freeze_time("2023-01-18 03:00:00+01:00")
def test_organizer_ok(event, user, team):
    djmail.outbox = []
    s = ScheduledOrganizerExport(organizer=event.organizer, owner=user)
    s.export_identifier = "eventdata"
    s.export_form_data = {"_format": "default", "all_events": True}
    s.mail_additional_recipients = "boss@example.org,boss@example.net"
    s.mail_additional_recipients_cc = "assistant@example.net"
    s.mail_additional_recipients_bcc = "archive@example.net"
    s.mail_subject = "Report 1"
    s.mail_template = "Here is the report."
    s.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s.schedule_rrule_time = time(2, 30, 0)
    s.schedule_next_run = now() - timedelta(minutes=5)
    s.error_counter = 1
    s.save()

    Event.objects.create(
        organizer=event.organizer, name='Dummy', slug='dummy2',
        date_from=datetime(2023, 1, 19, 2, 30, 0, tzinfo=timezone.utc),
        plugins='pretix.plugins.banktransfer'
    )

    run_scheduled_exports(None)
    s.refresh_from_db()
    assert s.schedule_next_run > now()
    assert s.error_counter == 0
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].subject == "Report 1"
    assert "Here is the report." in djmail.outbox[0].body
    assert djmail.outbox[0].to == ["boss@example.org", "boss@example.net"]
    assert djmail.outbox[0].cc == ["assistant@example.net", user.email]
    assert djmail.outbox[0].bcc == ["archive@example.net"]
    assert len(djmail.outbox[0].attachments) == 1
    assert djmail.outbox[0].attachments[0][0] == "dummy_events.csv"
    assert len(djmail.outbox[0].attachments[0][1].splitlines()) == 3
