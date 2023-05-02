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

from pretix.api.models import ApiCall
from pretix.base.models import Order

PAYLOAD = {
    "name": {
        "en": "Demo Conference 2020 Test"
    },
    "live": False,
    "testmode": True,
    "currency": "EUR",
    "date_from": "2018-12-27T10:00:00Z",
    "date_to": "2018-12-28T10:00:00Z",
    "date_admission": None,
    "is_public": False,
    "presale_start": None,
    "presale_end": None,
    "location": None,
    "slug": "2030",
}


@pytest.mark.django_db
def test_default(token_client, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json')
    assert resp.status_code == 201
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_scoped_by_key(token_client, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    d1 = resp
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    assert d1.data == json.loads(resp.content.decode())
    assert d1.headers._store == resp.headers._store
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='bar')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_concurrent(token_client, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    ApiCall.objects.all().update(locked=now())
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 409


@pytest.mark.django_db
def test_ignore_path_method_body(token_client, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             {}, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    resp = token_client.patch('/api/v1/organizers/{}/events/'.format(organizer.slug),
                              {}, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    resp = token_client.post('/api/v1/organizers/{}/§invalid/'.format(organizer.slug),
                             {}, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201


@pytest.mark.django_db
def test_query_key(token_client, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    data = resp.content
    resp = token_client.get('/api/v1/idempotency_query?key=foo')
    assert resp.content == data
    assert resp.status_code == 201
    resp = token_client.get('/api/v1/idempotency_query?key=bar')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_scoped_by_token(token_client, device, organizer):
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 201
    token_client.credentials(HTTP_AUTHORIZATION='Device ' + device.api_token)
    resp = token_client.post('/api/v1/organizers/{}/events/'.format(organizer.slug),
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_ignore_get(token_client, organizer, event):
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug),
                            HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 200
    d1 = resp.data
    event.name = "foo"
    event.save()
    resp = token_client.get('/api/v1/organizers/{}/events/'.format(organizer.slug),
                            HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 200
    assert d1 != json.loads(resp.content.decode())


@pytest.mark.django_db
def test_ignore_outside_api(token_client, organizer):
    resp = token_client.post('/control/login',
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 200
    resp = token_client.post('/control/invalid/',
                             PAYLOAD, format='json', HTTP_X_IDEMPOTENCY_KEY='foo')
    assert resp.status_code == 302


@pytest.fixture
def order(event):
    return Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PENDING, secret="k24fiuwvu8kxz3y1",
        datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
        total=23, locale='en'
    )


@pytest.mark.django_db
def test_allow_retry_409(token_client, organizer, event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    with event.lock():
        resp = token_client.post(
            '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
                organizer.slug, event.slug, order.code
            ), format='json', HTTP_X_IDEMPOTENCY_KEY='foo'
        )
        assert resp.status_code == 409
        order.refresh_from_db()
        assert order.status == Order.STATUS_EXPIRED
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/orders/{}/mark_paid/'.format(
            organizer.slug, event.slug, order.code
        ), format='json', HTTP_X_IDEMPOTENCY_KEY='foo'
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_PAID
