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
import datetime
import json

import pytest
from django.utils.timezone import now

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
    t = Team.objects.create(organizer=o, can_view_orders=True, can_change_orders=True, can_manage_customers=True,
                            can_change_event_settings=True)
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
    env[2].can_change_event_settings = False
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

    env[2].can_change_event_settings = True
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
    env[2].can_change_organizer_settings = False
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

    env[2].can_change_organizer_settings = True
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
