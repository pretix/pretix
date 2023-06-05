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
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Order, OrderPosition

SAMPLE_SHREDDER_CONFIG = {
    "identifier": "question_answers",
    "verbose_name": "Question answers",
}


@pytest.fixture
@scopes_disabled()
def order(event, item):
    o = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
        datetime=datetime(2017, 12, 1, 10, 0, 0, tzinfo=timezone.utc),
        expires=datetime(2017, 12, 10, 10, 0, 0, tzinfo=timezone.utc),
        total=23, locale='en'
    )
    OrderPosition.objects.create(
        order=o,
        item=item,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'_legacy': "Peter"},
        secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        pseudonymization_id="ABCDEFGHKL",
    )
    return o


@pytest.mark.django_db
def test_event_list(token_client, organizer, event):
    event.has_subevents = True
    event.save()
    c = copy.deepcopy(SAMPLE_SHREDDER_CONFIG)
    resp = token_client.get('/api/v1/organizers/{}/events/{}/shredders/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert c in resp.data['results']

    resp = token_client.get(
        '/api/v1/organizers/{}/events/{}/shredders/question_answers/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert c == resp.data


@pytest.mark.django_db
def test_event_validate(token_client, organizer, team, event):
    event.date_from = now() + timedelta(days=3)
    event.date_to = now() + timedelta(days=4)
    event.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/shredders/export/'.format(organizer.slug, event.slug),
        data={
            'shredders': ['question_answers']
        }, format='json'
    )
    assert resp.status_code == 400
    assert resp.data == ["Your event needs to be over to use this feature."]


@pytest.mark.django_db
def test_run_success(token_client, order, organizer, team, event):
    event.date_from = now() - timedelta(days=91)
    event.date_to = now() - timedelta(days=90)
    event.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/shredders/export/'.format(organizer.slug, event.slug),
        data={
            'shredders': ['order_emails']
        }, format='json'
    )
    assert resp.status_code == 202
    assert "download" in resp.data
    assert "shred" in resp.data

    resp2 = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp2.status_code == 200
    assert resp2["Content-Type"] == "application/zip"

    resp3 = token_client.post("/" + resp.data["shred"].split("/", 3)[3])
    assert resp3.status_code == 202
    assert "status" in resp3.data

    resp4 = token_client.get("/" + resp3.data["status"].split("/", 3)[3])
    assert resp4.status_code == 410  # because we have no celery

    resp2 = token_client.get("/" + resp.data["download"].split("/", 3)[3])
    assert resp2.status_code == 404  # shredded now

    order.refresh_from_db()
    assert not order.email


@pytest.mark.django_db
def test_download_nonexisting(token_client, organizer, team, event):
    resp = token_client.get('/api/v1/organizers/{}/events/{}/shredders/download/{}/{}/'.format(
        organizer.slug, event.slug, uuid.uuid4(), uuid.uuid4()
    ))
    assert resp.status_code == 404
