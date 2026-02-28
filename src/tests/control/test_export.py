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
import datetime
import json

import pytest
from bs4 import BeautifulSoup
from django.utils.timezone import now
from tests.base import extract_form_fields

from pretix.base.models import (
    Event, Item, Organizer, ScheduledEventExport, ScheduledOrganizerExport,
    Team, User,
)


@pytest.fixture
def env():
    o = Organizer.objects.create(name="Dummy", slug="dummy")
    event = Event.objects.create(
        organizer=o, name="Dummy", slug="dummy",
        date_from=now(), plugins="pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy"
    )
    event.settings.set("ticketoutput_testdummy__enabled", True)
    user = User.objects.create_user("dummy@dummy.dummy", "dummy")
    t = Team.objects.create(organizer=o, all_event_permissions=True)
    t.members.add(user)
    t.limit_events.add(event)

    Item.objects.create(
        event=event, name="Early-bird ticket", category=None, default_price=23,
        admission=True, personalized=True
    )
    return event, user, t


@pytest.mark.django_db(transaction=True)
def test_event_export(client, env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/event/dummy/dummy/orders/export/?identifier=itemdata")
    assert b"Export format" in response.content
    response = client.post("/control/event/dummy/dummy/orders/export/do", {
        "exporter": "itemdata",
        "itemdata-_format": "default",
        "ajax": "1"
    })
    d = json.loads(response.content)
    assert d["ready"]
    assert d["success"]
    response = client.get(d["redirect"])
    assert len(b"".join(response.streaming_content).split(b"\n")) == 3


@pytest.mark.django_db(transaction=True)
def test_event_export_schedule(client, env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/event/dummy/dummy/orders/export/?identifier=itemdata")
    assert b"Export format" in response.content
    assert b"Repetition schedule" not in response.content

    # Start editing
    response = client.post("/control/event/dummy/dummy/orders/export/?identifier=itemdata", {
        "schedule": "yes",
        "exporter": "itemdata",
        "itemdata-_format": "default",
    })
    assert b"Export format" in response.content
    assert b"Repetition schedule" in response.content

    # Create schedule
    response = client.post("/control/event/dummy/dummy/orders/export/?identifier=itemdata", {
        "schedule": "save",
        "exporter": "itemdata",
        "itemdata-_format": "default",
        "schedule-schedule_rrule_time": "03:30",
        "rrule-dtstart": "2023-01-19",
        "rrule-interval": "1",
        "rrule-freq": "weekly",
        "rrule-end": "forever",
        "rrule-until": "2022-01-01",  # ignored
        "rrule-count": "10",  # ignored
        "rrule-monthly_same": "on",  # ignored
        "rrule-yearly_same": "on",  # ignored
        "schedule-mail_additional_recipients": "boss@example.net, friend@example.com",
        "schedule-locale": "en",
        "schedule-mail_subject": "Product data, my friend!",
        "schedule-mail_template": "Mail body"
    }, follow=True)
    assert b"Your export schedule has been saved. The next export will start around" in response.content

    s = env[0].scheduled_exports.get()
    assert s.owner == env[1]
    assert s.schedule_rrule == "DTSTART:20230119T000000\nRRULE:FREQ=WEEKLY"
    assert s.schedule_rrule_time == datetime.time(3, 30, 0)
    assert s.schedule_next_run > now()
    assert s.export_identifier == "itemdata"
    assert s.export_form_data == {"_format": "default"}
    assert s.locale == "en"
    assert s.mail_additional_recipients == "boss@example.net,friend@example.com"
    assert s.mail_subject == "Product data, my friend!"
    assert s.mail_template == "Mail body"

    # Schedule is in list
    response = client.get("/control/event/dummy/dummy/orders/export/")
    assert b"Product data, my friend!" in response.content

    # Edit schedule
    response = client.get(f"/control/event/dummy/dummy/orders/export/?identifier=itemdata&scheduled={s.pk}")
    assert b"Mail body" in response.content

    # Submit edited schedule
    response = client.post(f"/control/event/dummy/dummy/orders/export/?identifier=itemdata&scheduled={s.pk}", {
        "schedule": "save",
        "exporter": "itemdata",
        "itemdata-_format": "xlsx",
        "schedule-schedule_rrule_time": "03:30",
        "rrule-dtstart": "2023-01-10",
        "rrule-interval": "1",
        "rrule-freq": "weekly",
        "rrule-end": "until",
        "rrule-until": "2022-01-01",  # ignored
        "rrule-count": "1",
        "rrule-monthly_same": "on",  # ignored
        "rrule-yearly_same": "on",  # ignored
        "schedule-mail_additional_recipients": "boss@example.net, friend@example.com",
        "schedule-locale": "en",
        "schedule-mail_subject": "Product data, my friend!",
        "schedule-mail_template": "Mail body"
    }, follow=True)
    assert b"Your export schedule has been saved, but no next export is planned" in response.content
    s.refresh_from_db()
    assert s.schedule_next_run is None
    assert s.export_form_data == {"_format": "xlsx"}

    # Run
    response = client.post(f"/control/event/dummy/dummy/orders/export/{s.pk}/run")
    assert response.status_code == 302

    # Delete schedule
    response = client.get(f"/control/event/dummy/dummy/orders/export/{s.pk}/delete")
    assert b"Product data, my friend!" in response.content
    client.post(f"/control/event/dummy/dummy/orders/export/{s.pk}/delete")
    assert env[0].scheduled_exports.count() == 0


@pytest.mark.django_db(transaction=True)
def test_event_limited_permission(client, env):
    env[2].all_event_permissions = False
    env[2].limit_event_permissions = {"event.orders:read": True}
    env[2].save()
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")

    s1 = ScheduledEventExport(event=env[0], owner=env[1])
    s1.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s1.schedule_rrule_time = datetime.time(2, 30, 0)
    s1.error_counter = 5
    s1.mail_subject = "RULE1"
    s1.save()
    s2 = ScheduledEventExport(event=env[0], owner=user2)
    s2.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s2.schedule_rrule_time = datetime.time(2, 30, 0)
    s2.error_counter = 5
    s2.mail_subject = "RULE2"
    s2.save()

    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/event/dummy/dummy/orders/export/")
    assert b"RULE1" in response.content
    assert b"RULE2" not in response.content

    response = client.get(f"/control/event/dummy/dummy/orders/export/?identifier=itemdata&scheduled={s1.pk}")
    assert response.status_code == 200
    response = client.get(f"/control/event/dummy/dummy/orders/export/?identifier=itemdata&scheduled={s2.pk}")
    assert response.status_code == 404

    response = client.post(f"/control/event/dummy/dummy/orders/export/{s1.pk}/run")
    assert response.status_code == 302
    response = client.get(f"/control/event/dummy/dummy/orders/export/{s1.pk}/delete")
    assert response.status_code == 200
    response = client.post(f"/control/event/dummy/dummy/orders/export/{s2.pk}/run")
    assert response.status_code == 404
    response = client.get(f"/control/event/dummy/dummy/orders/export/{s2.pk}/delete")
    assert response.status_code == 404

    env[2].limit_event_permissions = {"event.settings.general:write": True, "event.orders:read": True}
    env[2].save()
    response = client.get("/control/event/dummy/dummy/orders/export/")
    assert b"RULE1" in response.content
    assert b"RULE2" in response.content
    response = client.get(f"/control/event/dummy/dummy/orders/export/?identifier=itemdata&scheduled={s2.pk}")
    assert response.status_code == 200
    response = client.get(f"/control/event/dummy/dummy/orders/export/{s2.pk}/delete")
    assert response.status_code == 200
    response = client.post(f"/control/event/dummy/dummy/orders/export/{s2.pk}/run")
    assert response.status_code == 302


@pytest.mark.django_db(transaction=True)
def test_organizer_export(client, env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/organizer/dummy/export/?identifier=eventdata")
    assert b"Export format" in response.content
    response = client.post("/control/organizer/dummy/export/do", {
        "exporter": "eventdata",
        "eventdata-_format": "default",
        "eventdata-all_events": "on",
        "ajax": "1"
    })
    d = json.loads(response.content)
    assert d["ready"]
    assert d["success"]
    response = client.get(d["redirect"])
    assert len(b"".join(response.streaming_content).split(b"\n")) == 3


@pytest.mark.django_db(transaction=True)
def test_organizer_export_schedule(client, env):
    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/organizer/dummy/export/?identifier=eventdata")
    assert b"Export format" in response.content
    assert b"Repetition schedule" not in response.content

    # Start editing
    response = client.post("/control/organizer/dummy/export/?identifier=eventdata", {
        "schedule": "yes",
        "exporter": "eventdata",
        "eventdata-_format": "default",
        "eventdata-all_events": "on",
    })
    assert b"Export format" in response.content
    assert b"Repetition schedule" in response.content

    # Create schedule
    response = client.post("/control/organizer/dummy/export/?identifier=eventdata", {
        "schedule": "save",
        "exporter": "eventdata",
        "eventdata-_format": "default",
        "eventdata-all_events": "on",
        "schedule-schedule_rrule_time": "03:30",
        "schedule-timezone": "Australia/Sydney",
        "rrule-dtstart": "2023-01-19",
        "rrule-interval": "1",
        "rrule-freq": "weekly",
        "rrule-end": "forever",
        "rrule-until": "2022-01-01",  # ignored
        "rrule-count": "10",  # ignored
        "rrule-monthly_same": "on",  # ignored
        "rrule-yearly_same": "on",  # ignored
        "schedule-mail_additional_recipients": "boss@example.net, friend@example.com",
        "schedule-locale": "en",
        "schedule-mail_subject": "Product data, my friend!",
        "schedule-mail_template": "Mail body"
    }, follow=True)
    assert b"Your export schedule has been saved. The next export will start around" in response.content

    s = env[0].organizer.scheduled_exports.get()
    assert s.owner == env[1]
    assert s.schedule_rrule == "DTSTART:20230119T000000\nRRULE:FREQ=WEEKLY"
    assert s.schedule_rrule_time == datetime.time(3, 30, 0)
    assert s.schedule_next_run > now()
    assert s.export_identifier == "eventdata"
    assert s.export_form_data == {"_format": "default", "all_events": True, "events": []}
    assert s.locale == "en"
    assert s.timezone == "Australia/Sydney"
    assert s.mail_additional_recipients == "boss@example.net,friend@example.com"
    assert s.mail_subject == "Product data, my friend!"
    assert s.mail_template == "Mail body"

    # Schedule is in list
    response = client.get("/control/organizer/dummy/export/")
    assert b"Product data, my friend!" in response.content

    # Edit schedule
    response = client.get(f"/control/organizer/dummy/export/?identifier=eventdata&scheduled={s.pk}")
    assert b"Mail body" in response.content

    # Submit edited schedule
    response = client.post(f"/control/organizer/dummy/export/?identifier=eventdata&scheduled={s.pk}", {
        "schedule": "save",
        "exporter": "eventdata",
        "eventdata-all_events": "on",
        "eventdata-_format": "xlsx",
        "schedule-schedule_rrule_time": "03:30",
        "schedule-timezone": "Australia/Sydney",
        "rrule-dtstart": "2023-01-10",
        "rrule-interval": "1",
        "rrule-freq": "weekly",
        "rrule-end": "until",
        "rrule-until": "2022-01-01",  # ignored
        "rrule-count": "1",
        "rrule-monthly_same": "on",  # ignored
        "rrule-yearly_same": "on",  # ignored
        "schedule-mail_additional_recipients": "boss@example.net, friend@example.com",
        "schedule-locale": "en",
        "schedule-mail_subject": "Product data, my friend!",
        "schedule-mail_template": "Mail body"
    }, follow=True)
    assert b"Your export schedule has been saved, but no next export is planned" in response.content
    s.refresh_from_db()
    assert s.schedule_next_run is None
    assert s.export_form_data == {"_format": "xlsx", "all_events": True, "events": []}

    # Delete schedule
    response = client.post(f"/control/organizer/dummy/export/{s.pk}/run")
    assert response.status_code == 302

    # Delete schedule
    response = client.get(f"/control/organizer/dummy/export/{s.pk}/delete")
    assert b"Product data, my friend!" in response.content
    client.post(f"/control/organizer/dummy/export/{s.pk}/delete")
    assert env[0].organizer.scheduled_exports.count() == 0


@pytest.mark.django_db(transaction=True)
def test_organizer_limited_permission(client, env):
    env[2].all_organizer_permissions = False
    env[2].all_event_permissions = True
    env[2].save()
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")

    s1 = ScheduledOrganizerExport(organizer=env[0].organizer, owner=env[1])
    s1.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s1.schedule_rrule_time = datetime.time(2, 30, 0)
    s1.error_counter = 5
    s1.mail_subject = "RULE1"
    s1.save()
    s2 = ScheduledOrganizerExport(organizer=env[0].organizer, owner=user2)
    s2.schedule_rrule = "DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO"
    s2.schedule_rrule_time = datetime.time(2, 30, 0)
    s2.error_counter = 5
    s2.mail_subject = "RULE2"
    s2.save()

    client.login(email="dummy@dummy.dummy", password="dummy")
    response = client.get("/control/organizer/dummy/export/")
    assert b"RULE1" in response.content
    assert b"RULE2" not in response.content

    response = client.get(f"/control/organizer/dummy/export/?identifier=eventdata&scheduled={s1.pk}")
    assert response.status_code == 200
    response = client.get(f"/control/organizer/dummy/export/?identifier=eventdata&scheduled={s2.pk}")
    assert response.status_code == 404

    response = client.get(f"/control/organizer/dummy/export/{s1.pk}/delete")
    assert response.status_code == 200
    response = client.post(f"/control/organizer/dummy/export/{s1.pk}/run")
    assert response.status_code == 302
    response = client.get(f"/control/organizer/dummy/export/{s2.pk}/delete")
    assert response.status_code == 404
    response = client.post(f"/control/organizer/dummy/export/{s2.pk}/run")
    assert response.status_code == 404

    env[2].limit_organizer_permissions = {"organizer.settings.general:write": True}
    env[2].save()
    response = client.get("/control/organizer/dummy/export/")
    assert b"RULE1" in response.content
    assert b"RULE2" in response.content
    response = client.get(f"/control/organizer/dummy/export/?identifier=eventdata&scheduled={s2.pk}")
    assert response.status_code == 200
    response = client.get(f"/control/organizer/dummy/export/{s2.pk}/delete")
    assert response.status_code == 200
    response = client.post(f"/control/organizer/dummy/export/{s2.pk}/run")
    assert response.status_code == 302


def _can_see_but_not_edit_org_export(client, user, scheduled):
    client.login(email=user.email, password="dummy")

    response = client.get("/control/organizer/dummy/export/")
    assert f"export/{scheduled.pk}/delete".encode() in response.content
    response = client.get(f"/control/organizer/dummy/export/?identifier={scheduled.export_identifier}&scheduled={scheduled.pk}")
    if response.status_code == 404:
        return False

    assert response.status_code == 200
    doc = BeautifulSoup(response.content, "lxml")
    form_data = extract_form_fields(doc.select("form[data-asynctask]")[0])
    form_data["schedule"] = "save"

    response = client.post(f"/control/organizer/dummy/export/?identifier={scheduled.export_identifier}&scheduled={scheduled.pk}",
                           data=form_data, follow=True)
    assert response.status_code == 200

    return b"alert-success" in response.content and b"does not have sufficient permission" not in response.content


@pytest.mark.django_db(transaction=True)
def test_organizer_edit_restrictions(client, env):
    # This tests the prevention of a possible privilege escalation where user A creates a scheduled export and
    # user B has settings permission (= they can see the export configuration), but not enough permission
    # to run the export themselves. Without this check, user B could modify the export and add themselves
    # as a recipient. Thereby, user B would gain access to data they can't have.
    user1 = env[1]
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")

    event1 = env[0]
    event2 = Event.objects.create(
        organizer=env[0].organizer, name="Dummy", slug="dummy2",
        date_from=now(), plugins="pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy"
    )

    team1 = env[2]
    team1.all_organizer_permissions = False
    team1.all_event_permissions = False
    team1.all_events = False
    team1.limit_organizer_permissions = {"organizer.settings.general:write": True}
    team1.limit_event_permissions = {"event.orders:read": True, "event.settings.general:write": True}
    team1.save()
    team1.limit_events.add(event1)

    team2 = env[0].organizer.teams.create(
        all_organizer_permissions=False, all_event_permissions=False, all_events=False,
        limit_event_permissions={"event.orders:read": True},
        limit_organizer_permissions={"organizer.giftcards:read": True}
    )
    team2.limit_events.add(event2)
    team2.members.add(user2)

    # Scenario 1
    # User 2 created an export for all events. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, but can't change it, because they
    # don't have access to all events.
    s1 = ScheduledOrganizerExport.objects.create(
        organizer=env[0].organizer,
        owner=user2,
        export_identifier="dummy_orders",
        export_form_data={"all_events": True, "events": []},
        mail_subject="Test",
        mail_template="Test",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=datetime.time(2, 30, 0)
    )
    assert _can_see_but_not_edit_org_export(client, user2, s1)
    assert not _can_see_but_not_edit_org_export(client, user1, s1)

    # Scenario 2
    # User 2 created an export for all events. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, and change it, because they
    # have access to all events.
    team1.all_events = True
    team1.save()
    assert _can_see_but_not_edit_org_export(client, user2, s1)
    assert _can_see_but_not_edit_org_export(client, user1, s1)

    # Scenario 3
    # User 2 created an export for a specific event. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, but can't change it, because they
    # don't have access to that event.
    team1.all_events = False
    team1.save()
    s1.export_form_data = {"all_events": False, "events": [event2.pk]}
    s1.save()
    assert _can_see_but_not_edit_org_export(client, user2, s1)
    assert not _can_see_but_not_edit_org_export(client, user1, s1)

    # Scenario 4
    # User 2 created an export for a specific event. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, and change it, because they
    # have access to that event.
    team1.limit_events.add(event2)
    assert _can_see_but_not_edit_org_export(client, user2, s1)
    assert _can_see_but_not_edit_org_export(client, user1, s1)

    # Scenario 5
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, but can't change it, because they lack
    # that special permission
    s2 = ScheduledOrganizerExport.objects.create(
        organizer=env[0].organizer,
        owner=user2,
        export_identifier="giftcardlist",
        mail_subject="Test",
        mail_template="Test",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=datetime.time(2, 30, 0)
    )
    assert _can_see_but_not_edit_org_export(client, user2, s2)
    assert not _can_see_but_not_edit_org_export(client, user1, s2)

    # Scenario 6
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, and change it, because they have
    # that special permission
    team1.limit_organizer_permissions["organizer.giftcards:read"] = True
    team1.save()
    assert _can_see_but_not_edit_org_export(client, user2, s2)
    assert _can_see_but_not_edit_org_export(client, user1, s2)


def _can_see_but_not_edit_event_export(client, user, scheduled):
    client.login(email=user.email, password="dummy")

    response = client.get("/control/event/dummy/dummy/orders/export/")
    assert f"export/{scheduled.pk}/delete".encode() in response.content
    response = client.get(f"/control/event/dummy/dummy/orders/export/?identifier={scheduled.export_identifier}&scheduled={scheduled.pk}")
    if response.status_code == 404:
        return False

    assert response.status_code == 200
    doc = BeautifulSoup(response.content, "lxml")
    form_data = extract_form_fields(doc.select("form[data-asynctask]")[0])
    form_data["schedule"] = "save"

    response = client.post(f"/control/event/dummy/dummy/orders/export/?identifier={scheduled.export_identifier}&scheduled={scheduled.pk}",
                           data=form_data, follow=True)
    assert response.status_code == 200

    return b"alert-success" in response.content and b"does not have sufficient permission" not in response.content


@pytest.mark.django_db(transaction=True)
def test_event_edit_restrictions(client, env):
    # This tests the prevention of a possible privilege escalation where user A creates a scheduled export and
    # user B has settings permission (= they can see the export configuration), but not enough permission
    # to run the export themselves. Without this check, user B could modify the export and add themselves
    # as a recipient. Thereby, user B would gain access to data they can't have.
    user1 = env[1]
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")
    event1 = env[0]

    team1 = env[2]
    team1.all_organizer_permissions = False
    team1.all_event_permissions = False
    team1.all_events = False
    team1.limit_organizer_permissions = {"organizer.settings.general:write": True}
    team1.limit_event_permissions = {"event.orders:read": True, "event.settings.general:write": True}
    team1.save()
    team1.limit_events.add(event1)

    team2 = env[0].organizer.teams.create(
        all_organizer_permissions=False, all_event_permissions=False, all_events=False,
        limit_event_permissions={"event.orders:read": True, "event.vouchers:read": True},
        limit_organizer_permissions={"organizer.giftcards:read": True}
    )
    team2.limit_events.add(event1)
    team2.members.add(user2)

    s2 = ScheduledEventExport.objects.create(
        event=event1,
        owner=user2,
        export_identifier="dummy_vouchers",
        mail_subject="Test",
        mail_template="Test",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=datetime.time(2, 30, 0)
    )
    assert _can_see_but_not_edit_event_export(client, user2, s2)
    assert not _can_see_but_not_edit_event_export(client, user1, s2)

    # Scenario 6
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, and change it, because they have
    # that special permission
    team1.limit_event_permissions["event.vouchers:read"] = True
    team1.save()
    assert _can_see_but_not_edit_event_export(client, user2, s2)
    assert _can_see_but_not_edit_event_export(client, user1, s2)
