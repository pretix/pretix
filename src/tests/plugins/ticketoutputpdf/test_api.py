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
import copy
import json

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from pretix.base.models import Event, Item, Organizer, Team
from pretix.plugins.ticketoutputpdf.models import TicketLayoutItem


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer'
    )
    t = Team.objects.create(organizer=event.organizer)
    t.limit_events.add(event)
    item1 = Item.objects.create(event=event, name="Ticket", default_price=23)
    tl = event.ticket_layouts.create(name="Foo", default=True, layout='[{"a": 2}]')
    TicketLayoutItem.objects.create(layout=tl, item=item1)
    return event, tl, item1


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
@scopes_disabled()
def token_client(client, env):
    t = env[0].organizer.teams.get().tokens.create(name="Foo")
    client.credentials(HTTP_AUTHORIZATION="Token " + t.token)
    return client


RES_LAYOUT = {
    'id': 1,
    'name': 'Foo',
    'default': True,
    'item_assignments': [{'item': 1, 'sales_channel': 'web'}],
    'layout': [{'a': 2}],
    'background': 'http://example.com/static/pretixpresale/pdf/ticket_default_a4.pdf'
}


@pytest.mark.django_db
def test_api_list(env, token_client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[1].pk
    res['item_assignments'][0]['item'] = env[2].pk
    r = token_client.get('/api/v1/organizers/{}/events/{}/ticketlayouts/'.format(
        env[0].organizer.slug, env[0].slug)).data

    assert r['results'] == [res]
    r = token_client.get('/api/v1/organizers/{}/events/{}/ticketlayoutitems/'.format(
        env[0].organizer.slug, env[0].slug)).data
    assert r['results'] == [{'item': env[2].pk, 'layout': env[1].pk, 'id': env[1].item_assignments.first().pk,
                             'sales_channel': 'web'}]


@pytest.mark.django_db
def test_api_detail(env, token_client):
    res = copy.copy(RES_LAYOUT)
    res['id'] = env[1].pk
    res['item_assignments'][0]['item'] = env[2].pk
    r = token_client.get('/api/v1/organizers/{}/events/{}/ticketlayouts/{}/'.format(
        env[0].organizer.slug, env[0].slug, env[1].pk)).data
    assert r == res


@pytest.mark.django_db
def test_api_create(env, token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('file.pdf', 'invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.pdf"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/'.format(env[0].slug, env[0].slug),
        {
            'name': 'Foo',
            'default': False,
            "background": file_id_png,
            'layout': [],
        },
        format='json'
    )
    assert resp.status_code == 201
    tl = env[0].ticket_layouts.get(pk=resp.data["id"])
    assert tl.background


@pytest.mark.django_db
def test_api_create_validate_default(env, token_client):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/'.format(env[0].slug, env[0].slug),
        {
            'name': 'Foo',
            'default': True,
            'layout': [],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {"non_field_errors": ["You cannot have two layouts with default = True"]}


@pytest.mark.django_db
def test_api_create_validate_layout(env, token_client):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/'.format(env[0].slug, env[0].slug),
        {
            'name': 'Foo',
            'default': True,
            'layout': [
                {
                    "foo": "bar"
                }
            ],
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data["layout"][0].startswith("Your layout file is not a valid layout. Error message:")


@pytest.mark.django_db
def test_api_update(env, token_client):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'application/pdf',
            'file': ContentFile('file.pdf', 'invalid pdf content')
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.pdf"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']

    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/{}/'.format(env[0].slug, env[0].slug, env[1].pk),
        {
            "name": "Bar",
            "background": file_id_png,
            "layout": [
                {"type": "barcodearea", "left": "7.00", "bottom": "11.15", "size": "45.00", "content": "secret"}
            ]
        },
        format='json'
    )
    assert resp.status_code == 200
    env[1].refresh_from_db()
    assert env[1].name == "Bar"
    assert env[1].background
    assert json.loads(env[1].layout) == [
        {"type": "barcodearea", "left": "7.00", "bottom": "11.15", "size": "45.00", "content": "secret"}
    ]


@pytest.mark.django_db
def test_api_update_validate_default(env, token_client):
    tl2 = env[0].ticket_layouts.create(name="Foo", default=False, layout='[{"a": 2}]')
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/{}/'.format(env[0].slug, env[0].slug, tl2.pk),
        {
            "default": True,
        },
        format='json'
    )
    assert resp.status_code == 400
    assert resp.data == {"non_field_errors": ["You cannot have two layouts with default = True"]}


@pytest.mark.django_db
def test_api_delete(env, token_client):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/ticketlayouts/{}/'.format(env[0].slug, env[0].slug, env[1].pk),
    )
    assert resp.status_code == 204
    assert not env[0].ticket_layouts.exists()
