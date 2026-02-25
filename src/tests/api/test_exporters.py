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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Benjamin Hättasch
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import uuid
import zoneinfo
from datetime import time

import pytest
from django.utils.timezone import now
from rest_framework.test import APIClient

from pretix.base.models import (
    CachedFile, Event, ScheduledEventExport, ScheduledOrganizerExport, User,
)

SAMPLE_EXPORTER_CONFIG = {
    "identifier": "orderlist",
    "verbose_name": "Order data",
    "input_parameters": [
        {
            "name": "_format",
            "required": True,
            "choices": [
                "xlsx",
                "orders:default",
                "orders:excel",
                "orders:semicolon",
                "positions:default",
                "positions:excel",
                "positions:semicolon",
                "fees:default",
                "fees:excel",
                "fees:semicolon"
            ]
        },
        {
            "name": "paid_only",
            "required": False
        },
        {
            "name": "include_payment_amounts",
            "required": False
        },
        {
            "name": "group_multiple_choice",
            "required": False
        },
        {
            "name": "date_range",
            "required": False
        },
        {
            "name": "event_date_range",
            "required": False
        },
        {
            "name": "items",
            "required": False
        },
    ]
}


@pytest.mark.django_db
def test_event_list(token_client, organizer, event):
    event.has_subevents = True
    event.save()
    c = copy.deepcopy(SAMPLE_EXPORTER_CONFIG)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/exporters/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert c in resp.data['results']

    resp = token_client.get('/api/v1/organizers/{}/events/{}/exporters/orderlist/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert c == resp.data


@pytest.mark.django_db
def test_org_list(token_client, organizer, event):
    c = copy.deepcopy(SAMPLE_EXPORTER_CONFIG)
    c['input_parameters'].insert(0, {
        "name": "events",
        "required": False
    })
    c['input_parameters'].insert(0, {
        "name": "all_events",
        "required": False
    })
    c['input_parameters'].remove({
        "name": "items",
        "required": False
    })
    resp = token_client.get('/api/v1/organizers/{}/exporters/'.format(organizer.slug))
    assert resp.status_code == 200
    assert c in resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/exporters/orderlist/'.format(organizer.slug))
    assert resp.status_code == 200
    assert c == resp.data


@pytest.mark.django_db
def test_event_validate(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"_format": ["This field is required."]}

    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
        '_format': 'FOOBAR',
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"_format": ["\"FOOBAR\" is not a valid choice."]}


@pytest.mark.django_db(transaction=True)
def test_org_validate_events(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/exporters/orderlist/run/'.format(organizer.slug), data={
        '_format': 'xlsx',
    }, format='json')
    assert resp.status_code == 202

    resp = token_client.post('/api/v1/organizers/{}/exporters/orderlist/run/'.format(organizer.slug), data={
        '_format': 'xlsx',
        'events': ["nonexisting"]
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"events": ["Object with slug=nonexisting does not exist."]}

    resp = token_client.post('/api/v1/organizers/{}/exporters/orderlist/run/'.format(organizer.slug), data={
        'events': [event.slug],
        '_format': 'xlsx'
    }, format='json')
    assert resp.status_code == 202

    team.all_events = False
    team.save()

    resp = token_client.post('/api/v1/organizers/{}/exporters/orderlist/run/'.format(organizer.slug), data={
        '_format': 'xlsx',
        'events': [event.slug]
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"events": [f"Object with slug={event.slug} does not exist."]}


@pytest.mark.django_db(transaction=True)
def test_org_run_limit_events(token_client, organizer, team, event, event2):
    resp = token_client.post('/api/v1/organizers/{}/exporters/eventdata/run/'.format(organizer.slug), data={
        '_format': 'default',
    }, format='json')
    assert resp.status_code == 202
    assert "download" in resp.data
    resp = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp.status_code == 200
    assert resp.getvalue().strip().count(b"\n") == 2

    resp = token_client.post('/api/v1/organizers/{}/exporters/eventdata/run/'.format(organizer.slug), data={
        '_format': 'default',
        'events': [event.slug],
    }, format='json')
    assert resp.status_code == 202
    assert "download" in resp.data
    resp = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp.status_code == 200
    assert resp.getvalue().strip().count(b"\n") == 1

    team.all_events = False
    team.limit_events.add(event)
    team.save()

    resp = token_client.post('/api/v1/organizers/{}/exporters/eventdata/run/'.format(organizer.slug), data={
        '_format': 'default',
    }, format='json')
    assert resp.status_code == 202
    assert "download" in resp.data
    resp = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp.status_code == 200
    assert resp.getvalue().strip().count(b"\n") == 1


@pytest.mark.django_db(transaction=True)
def test_run_success(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
        '_format': 'xlsx',
        'date_range': 'year_this'
    }, format='json')
    assert resp.status_code == 202
    assert "download" in resp.data
    resp = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.django_db(transaction=True)
def test_run_success_old_date_frame(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
        '_format': 'xlsx',
        'date_from': '2020-01-01',
        'date_to': '2023-12-31'
    }, format='json')
    assert resp.status_code == 202
    assert "download" in resp.data
    resp = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.django_db
def test_run_date_frame_validation(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
        '_format': 'xlsx',
        'date_range': 'invalid'
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"date_range": ["Invalid date frame"]}


@pytest.mark.django_db
def test_run_additional_fields_forbidden(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/events/{}/exporters/orderlist/run/'.format(organizer.slug, event.slug), data={
        '_format': 'xlsx',
        'foobar': 'invalid'
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"fields": ["Additional fields not allowed: ['foobar']."]}


@pytest.mark.django_db
def test_download_nonexisting(token_client, organizer, team, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/exporters/orderlist/download/{}/{}/'.format(
        organizer.slug, event.slug, uuid.uuid4(), uuid.uuid4()
    ))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_gone_without_celery(token_client, organizer, team, event):
    cf = CachedFile.objects.create()
    resp = token_client.get('/api/v1/organizers/{}/events/{}/exporters/orderlist/download/{}/{}/'.format(organizer.slug, event.slug, uuid.uuid4(), cf.id))
    assert resp.status_code == 410


@pytest.mark.django_db(transaction=True)
def test_org_level_export(token_client, organizer, team, event):
    resp = token_client.post('/api/v1/organizers/{}/exporters/giftcardlist/run/'.format(organizer.slug), data={
        'date': '2022-10-05T00:00:00Z',
        '_format': 'xlsx',
    }, format='json')
    assert resp.status_code == 202

    team.limit_organizer_permissions = {"organizer.events:create": True}
    team.all_organizer_permissions = False
    team.save()

    resp = token_client.post('/api/v1/organizers/{}/exporters/giftcardlist/run/'.format(organizer.slug), data={
        'date': '2022-10-05T00:00:00Z',
        '_format': 'xlsx',
    }, format='json')
    assert resp.status_code == 404


@pytest.fixture
def event_scheduled_export(event, user):
    e = event.scheduled_exports.create(
        owner=user,
        export_identifier="orderlist",
        export_form_data={
            "_format": "xlsx",
            "date_range": "year_this"
        },
        locale="en",
        mail_additional_recipients="foo@example.org",
        mail_subject="Current order list",
        mail_template="Here is the current order list",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        schedule_rrule_time=time(4, 0, 0),
    )
    e.compute_next_run()
    e.save()
    return e


TEST_SCHEDULED_EXPORT_RES = {
    "owner": "dummy@dummy.dummy",
    "export_identifier": "orderlist",
    "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
    "locale": "en",
    "mail_additional_recipients": "foo@example.org",
    "mail_additional_recipients_cc": "",
    "mail_additional_recipients_bcc": "",
    "mail_subject": "Current order list",
    "mail_template": "Here is the current order list",
    "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
    "schedule_rrule_time": "04:00:00",
    "error_counter": 0,
}


@pytest.mark.django_db
def test_event_scheduled_export_list_token(token_client, organizer, event, user, team, event_scheduled_export):
    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = event_scheduled_export.pk
    res["schedule_next_run"] = event_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")). \
        isoformat().replace("+00:00", "Z")

    # Token can see it because it has change permission
    resp = token_client.get('/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    team.limit_organizer_permissions = {"organizer.events:create": True}
    team.all_organizer_permissions = False
    team.all_event_permissions = False
    team.save()

    # Token can no longer sees it and gets error message
    resp = token_client.get('/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_event_scheduled_export_list_user(user_client, organizer, event, user, team, event_scheduled_export):
    user2 = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    team.members.add(user2)

    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = event_scheduled_export.pk
    res["schedule_next_run"] = event_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")).\
        isoformat().replace("+00:00", "Z")

    # User can see it because its their own
    resp = user_client.get('/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']

    team.all_organizer_permissions = False
    team.limit_event_permissions = {"event.orders:read": True}
    team.all_event_permissions = False
    team.save()

    # Owner still can
    resp = user_client.get('/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug))
    assert [res] == resp.data['results']

    # Other user can't see it and gets empty list
    user_client.force_authenticate(user=user2)
    resp = user_client.get('/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_event_scheduled_export_detail(token_client, organizer, event, user, event_scheduled_export):
    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = event_scheduled_export.pk
    res["schedule_next_run"] = event_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")).\
        isoformat().replace("+00:00", "Z")

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/{}/'.format(
            organizer.slug, event.slug, event_scheduled_export.pk
        )
    )
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_event_scheduled_export_create(user_client, organizer, event, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this", "items": []},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 201
    created = event.scheduled_exports.get(id=resp.data["id"])
    assert created.export_form_data == {"_format": "xlsx", "date_range": "year_this", "items": []}
    assert created.owner == user
    assert created.schedule_next_run > now()


@pytest.mark.django_db
def test_event_scheduled_export_create_requires_user(token_client, organizer, event, user):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/'.format(organizer.slug, event.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this", "items": []},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_event_scheduled_export_delete_token(token_client, organizer, event, user, event_scheduled_export):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/{}/'.format(
            organizer.slug, event.slug, event_scheduled_export.pk,
        ),
    )
    assert resp.status_code == 204
    assert not event.scheduled_exports.exists()


@pytest.mark.django_db
def test_event_scheduled_export_update_token(token_client, organizer, event, user, event_scheduled_export):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/{}/'.format(
            organizer.slug, event.slug, event_scheduled_export.pk,
        ),
        data={
            "export_form_data": {"_format": "xlsx", "date_range": "month_this"},
        },
        format='json'
    )
    assert resp.status_code == 200
    created = event.scheduled_exports.get(id=resp.data["id"])
    assert created.export_form_data == {"_format": "xlsx", "date_range": "month_this", "items": []}


@pytest.fixture
def org_scheduled_export(organizer, user):
    e = organizer.scheduled_exports.create(
        owner=user,
        export_identifier="orderlist",
        export_form_data={
            "_format": "xlsx",
            "date_range": "year_this"
        },
        locale="en",
        mail_additional_recipients="foo@example.org",
        mail_subject="Current order list",
        mail_template="Here is the current order list",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
        schedule_rrule_time=time(4, 0, 0),
    )
    e.compute_next_run()
    e.save()
    return e


@pytest.mark.django_db
def test_org_scheduled_export_list_token(token_client, organizer, user, team, org_scheduled_export):
    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = org_scheduled_export.pk
    res["schedule_next_run"] = org_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")). \
        isoformat().replace("+00:00", "Z")
    res["timezone"] = "UTC"

    # Token can see it because it has change permission
    resp = token_client.get('/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']

    team.limit_organizer_permissions = {"organizer.events:create": True}
    team.all_organizer_permissions = False
    team.save()

    # Token can no longer sees it an gets error message
    resp = token_client.get('/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_org_scheduled_export_list_user(user_client, organizer, user, team, org_scheduled_export):
    user2 = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    team.members.add(user2)

    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = org_scheduled_export.pk
    res["schedule_next_run"] = org_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")). \
        isoformat().replace("+00:00", "Z")
    res["timezone"] = "UTC"

    # User can see it because its their own
    resp = user_client.get('/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug))
    assert [res] == resp.data['results']

    team.limit_organizer_permissions = {"organizer.events:create": True}
    team.all_organizer_permissions = False
    team.save()

    # Owner still can
    resp = user_client.get('/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug))
    assert [res] == resp.data['results']

    # Other user can't see it and gets empty list
    user_client.force_authenticate(user=user2)
    resp = user_client.get('/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_org_scheduled_export_detail(token_client, organizer, user, org_scheduled_export):
    res = dict(TEST_SCHEDULED_EXPORT_RES)
    res["id"] = org_scheduled_export.pk
    res["schedule_next_run"] = org_scheduled_export.schedule_next_run.astimezone(zoneinfo.ZoneInfo("UTC")). \
        isoformat().replace("+00:00", "Z")
    res["timezone"] = "UTC"

    resp = token_client.get(
        '/api/v1/organizers/{}/scheduled_exports/{}/'.format(
            organizer.slug, org_scheduled_export.pk
        )
    )
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_org_scheduled_export_create(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 201
    created = organizer.scheduled_exports.get(id=resp.data["id"])
    assert created.export_form_data == {"_format": "xlsx", "date_range": "year_this", "event_date_range": "/"}
    assert created.owner == user
    assert created.schedule_next_run > now()


@pytest.mark.django_db
def test_org_scheduled_export_create_requires_user(token_client, organizer, user):
    resp = token_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_org_scheduled_export_delete_token(token_client, organizer, user, org_scheduled_export):
    resp = token_client.delete(
        '/api/v1/organizers/{}/scheduled_exports/{}/'.format(
            organizer.slug, org_scheduled_export.pk,
        ),
    )
    assert resp.status_code == 204
    assert not organizer.scheduled_exports.exists()


@pytest.mark.django_db
def test_org_scheduled_export_update_token(token_client, organizer, user, org_scheduled_export):
    resp = token_client.patch(
        '/api/v1/organizers/{}/scheduled_exports/{}/'.format(
            organizer.slug, org_scheduled_export.pk,
        ),
        data={
            "export_form_data": {"_format": "xlsx", "date_range": "month_this"},
            "timezone": "America/New_York"
        },
        format='json'
    )
    assert resp.status_code == 200
    created = organizer.scheduled_exports.get(id=resp.data["id"])
    assert created.export_form_data == {"_format": "xlsx", "date_range": "month_this", "event_date_range": "/"}
    assert created.timezone == "America/New_York"


@pytest.mark.django_db
def test_org_scheduled_export_validate_identifier(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "unknownorg",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"export_identifier": ["\"unknownorg\" is not a valid choice."]}


@pytest.mark.django_db
def test_org_scheduled_export_validate_form_data(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "UNKNOWN"},
            "locale": "en",
            "mail_additional_recipients": "foo@example.org",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"export_form_data": {"date_range": ["Invalid date frame"]}}


@pytest.mark.django_db
def test_org_scheduled_export_validate_locale(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "BLÖDSINN",
            "mail_additional_recipients": "",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"locale": ["\"BLÖDSINN\" is not a valid choice."]}


@pytest.mark.django_db
def test_org_scheduled_export_validate_timezone(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "de",
            "mail_additional_recipients": "",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
            "timezone": "Invalid"
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"timezone": ["\"Invalid\" is not a valid choice."]}


@pytest.mark.django_db
def test_org_scheduled_export_validate_additional_recipients(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "aaaaaa",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"mail_additional_recipients": ["Enter a valid email address."]}

    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,"
                                          "a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,"
                                          "a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com,a@b.com",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"mail_additional_recipients": ["Please enter less than 25 recipients."]}


@pytest.mark.django_db
def test_org_scheduled_export_validate_rrule(user_client, organizer, user):
    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "invalid content",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"schedule_rrule": ["Not a valid rrule."]}

    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH\nEXRULE:FREQ=WEEKLY;COUNT=4;INTERVAL=2;BYDAY=TU,TH",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"schedule_rrule": ["Only a single RRULE is allowed, no combination of rules."]}

    resp = user_client.post(
        '/api/v1/organizers/{}/scheduled_exports/'.format(organizer.slug),
        data={
            "export_identifier": "orderlist",
            "export_form_data": {"_format": "xlsx", "date_range": "year_this"},
            "locale": "en",
            "mail_additional_recipients": "",
            "mail_additional_recipients_cc": "",
            "mail_additional_recipients_bcc": "",
            "mail_subject": "Current order list",
            "mail_template": "Here is the current order list",
            "schedule_rrule": "DTSTART:20230118T000000\nRRULE:FREQ=YEARLY;BYEASTER=0",
            "schedule_rrule_time": "04:00:00",
        },
        format='json',
    )
    assert resp.status_code == 400
    assert resp.data == {"schedule_rrule": ["BYEASTER not supported"]}


def _can_see_but_not_edit_org_export(client, scheduled):
    response = client.get(
        '/api/v1/organizers/{}/scheduled_exports/{}/'.format("dummy", scheduled.pk),
    )
    assert response.status_code == 200

    response = client.patch(
        '/api/v1/organizers/{}/scheduled_exports/{}/'.format("dummy", scheduled.pk),
        data=response.data,
        format='json',
    )
    return response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_organizer_edit_restrictions(client, event, organizer, user, team):
    # This tests the prevention of a possible privilege escalation where user A creates a scheduled export and
    # user B has settings permission (= they can see the export configuration), but not enough permission
    # to run the export themselves. Without this check, user B could modify the export and add themselves
    # as a recipient. Thereby, user B would gain access to data they can't have.
    user1_client = APIClient()
    user1_client.force_authenticate(user=user)
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")
    user2_client = APIClient()
    user2_client.force_authenticate(user=user2)
    team1_client = APIClient()
    t = team.tokens.create(name='Foo')
    team1_client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)

    event1 = event
    event2 = Event.objects.create(
        organizer=organizer, name="Dummy", slug="dummy2",
        date_from=now(), plugins="pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy"
    )

    team1 = team
    team1.all_organizer_permissions = False
    team1.all_event_permissions = False
    team1.all_events = False
    team1.limit_organizer_permissions = {"organizer.settings.general:write": True}
    team1.limit_event_permissions = {"event.orders:read": True, "event.settings.general:write": True}
    team1.save()
    team1.limit_events.add(event1)
    team1.members.add(user)

    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)

    team2 = organizer.teams.create(
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
        organizer=organizer,
        owner=user2,
        export_identifier="dummy_orders",
        export_form_data={"all_events": True, "events": []},
        mail_subject="Test",
        mail_template="Test",
        locale="en",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=time(2, 30, 0)
    )
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s1)
    assert not _can_see_but_not_edit_org_export(user1_client, s1)
    assert not _can_see_but_not_edit_org_export(team1_client, s1)

    # Scenario 2
    # User 2 created an export for all events. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, and change it, because they
    # have access to all events.
    team1.all_events = True
    team1.save()
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s1)
    assert _can_see_but_not_edit_org_export(user1_client, s1)
    assert _can_see_but_not_edit_org_export(team1_client, s1)

    # Scenario 3
    # User 2 created an export for a specific event. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, but can't change it, because they
    # don't have access to that event.
    team1.all_events = False
    team1.save()
    s1.export_form_data = {"all_events": False, "events": [event2.pk]}
    s1.save()
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s1)
    assert not _can_see_but_not_edit_org_export(user1_client, s1)
    assert not _can_see_but_not_edit_org_export(team1_client, s1)

    # Scenario 4
    # User 2 created an export for a specific event. User 2 can edit it, because they own it.
    # User 1 can see it, because they have permission to see scheduled exports, and change it, because they
    # have access to that event.
    team1.limit_events.add(event2)
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s1)
    assert _can_see_but_not_edit_org_export(user1_client, s1)
    assert _can_see_but_not_edit_org_export(team1_client, s1)

    # Scenario 5
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, but can't change it, because they lack
    # that special permission
    s2 = ScheduledOrganizerExport.objects.create(
        organizer=organizer,
        owner=user2,
        export_identifier="giftcardlist",
        mail_subject="Test",
        mail_template="Test",
        locale="en",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=time(2, 30, 0)
    )
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s2)
    assert not _can_see_but_not_edit_org_export(user1_client, s2)
    assert not _can_see_but_not_edit_org_export(team1_client, s2)

    # Scenario 6
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, and change it, because they have
    # that special permission
    team1.limit_organizer_permissions["organizer.giftcards:read"] = True
    team1.save()
    user._teamcache = {}
    assert _can_see_but_not_edit_org_export(user2_client, s2)
    assert _can_see_but_not_edit_org_export(team1_client, s2)
    assert _can_see_but_not_edit_org_export(user1_client, s2)


def _can_see_but_not_edit_event_export(client, scheduled):
    response = client.get(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/{}/'.format("dummy", "dummy", scheduled.pk),
    )
    assert response.status_code == 200

    response = client.patch(
        '/api/v1/organizers/{}/events/{}/scheduled_exports/{}/'.format("dummy", "dummy", scheduled.pk),
        data=response.data,
        format='json',
    )
    return response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_event_edit_restrictions(client, event, organizer, user, team):
    # This tests the prevention of a possible privilege escalation where user A creates a scheduled export and
    # user B has settings permission (= they can see the export configuration), but not enough permission
    # to run the export themselves. Without this check, user B could modify the export and add themselves
    # as a recipient. Thereby, user B would gain access to data they can't have.
    user1_client = APIClient()
    user1_client.force_authenticate(user=user)
    user2 = User.objects.create_user("dummy2@dummy.dummy", "dummy")
    user2_client = APIClient()
    user2_client.force_authenticate(user=user2)
    team1_client = APIClient()
    t = team.tokens.create(name='Foo')
    team1_client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)

    event1 = event

    team1 = team
    team1.all_organizer_permissions = False
    team1.all_event_permissions = False
    team1.all_events = False
    team1.limit_organizer_permissions = {"organizer.settings.general:write": True}
    team1.limit_event_permissions = {"event.orders:read": True, "event.settings.general:write": True}
    team1.save()
    team1.limit_events.add(event1)
    team1.members.add(user)

    t = team.tokens.create(name='Foo')
    client.credentials(HTTP_AUTHORIZATION='Token ' + t.token)

    team2 = organizer.teams.create(
        all_organizer_permissions=False, all_event_permissions=False, all_events=False,
        limit_event_permissions={"event.orders:read": True, "event.vouchers:read": True},
        limit_organizer_permissions={"organizer.giftcards:read": True}
    )
    team2.limit_events.add(event1)
    team2.members.add(user2)

    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, but can't change it, because they lack
    # that special permission
    s2 = ScheduledEventExport.objects.create(
        event=event,
        owner=user2,
        export_identifier="dummy_vouchers",
        mail_subject="Test",
        mail_template="Test",
        locale="en",
        schedule_rrule="DTSTART:20230118T000000\nRRULE:FREQ=DAILY;INTERVAL=1;WKST=MO",
        schedule_rrule_time=time(2, 30, 0)
    )
    user._teamcache = {}
    user2._teamcache = {}
    assert _can_see_but_not_edit_event_export(user2_client, s2)
    assert not _can_see_but_not_edit_event_export(user1_client, s2)
    assert not _can_see_but_not_edit_event_export(team1_client, s2)

    # Scenario 6
    # User 2 created an export that requires a special permission on organizer level
    # user 1 can see it, because they have permission to see scheduled exports, and change it, because they have
    # that special permission
    team1.limit_event_permissions["event.vouchers:read"] = True
    team1.save()
    user._teamcache = {}
    assert _can_see_but_not_edit_event_export(user2_client, s2)
    assert _can_see_but_not_edit_event_export(team1_client, s2)
    assert _can_see_but_not_edit_event_export(user1_client, s2)
