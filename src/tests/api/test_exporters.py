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

import pytest

from pretix.base.models import CachedFile

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
        'events': []
    }, format='json')
    assert resp.status_code == 400
    assert resp.data == {"events": ["This list may not be empty."]}

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

    team.can_manage_gift_cards = False
    team.save()

    resp = token_client.post('/api/v1/organizers/{}/exporters/giftcardlist/run/'.format(organizer.slug), data={
        'date': '2022-10-05T00:00:00Z',
        '_format': 'xlsx',
    }, format='json')
    assert resp.status_code == 404
