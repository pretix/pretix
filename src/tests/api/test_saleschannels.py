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
import pytest
from django_scopes import scopes_disabled


@pytest.mark.django_db
def test_channel_list(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/saleschannels/'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data['results'][0]["label"]["en"] == "Online shop"
    assert resp.data['results'][0]["position"] == 0
    assert resp.data['results'][0]["identifier"] == "web"
    assert resp.data['results'][0]["type"] == "web"


@pytest.mark.django_db
def test_channel_detail(token_client, organizer):
    resp = token_client.get('/api/v1/organizers/{}/saleschannels/web/'.format(organizer.slug))
    assert resp.status_code == 200
    assert resp.data["label"]["en"] == "Online shop"
    assert resp.data["position"] == 0
    assert resp.data["identifier"] == "web"
    assert resp.data["type"] == "web"


@pytest.mark.django_db
def test_channel_create(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/saleschannels/'.format(organizer.slug),
        format='json',
        data={
            "label": {
                "en": "API 1"
            },
            "type": "api",
            "identifier": "api.1",
            "position": 5,
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        sc = organizer.sales_channels.get(identifier="api.1")
        assert sc.type == "api"
        assert sc.identifier == "api.1"
        assert sc.position == 5


@pytest.mark.django_db
def test_channel_create_invalid(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/saleschannels/'.format(organizer.slug),
        format='json',
        data={
            "label": {
                "en": "API 1"
            },
            "type": "foo",
            "identifier": "api.1",
            "position": 5,
        }
    )
    assert resp.status_code == 400
    assert resp.data == {"type": ["You can currently only create channels of type 'api' through the API."]}

    resp = token_client.post(
        '/api/v1/organizers/{}/saleschannels/'.format(organizer.slug),
        format='json',
        data={
            "label": {
                "en": "API 1"
            },
            "type": "api",
            "identifier": "foo.1",
            "position": 5,
        }
    )
    assert resp.status_code == 400
    assert resp.data == {"identifier": ["Your identifier needs to start with 'api.'."]}

    resp = token_client.post(
        '/api/v1/organizers/{}/saleschannels/'.format(organizer.slug),
        format='json',
        data={
            "label": {
                "en": "API 1"
            },
            "type": "api",
            "identifier": "api.Ungültig",
            "position": 5,
        }
    )
    assert resp.status_code == 400
    assert resp.data == {"identifier": ["The identifier may only contain letters, numbers, dots, dashes, and underscores."]}


@pytest.mark.django_db
def test_channel_patch(token_client, organizer):
    resp = token_client.patch(
        '/api/v1/organizers/{}/saleschannels/web/'.format(organizer.slug),
        format='json',
        data={
            'label': {
                "en": "World Wide Web"
            },
            'position': 9000,
        }
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert str(organizer.sales_channels.get(identifier="web").label) == "World Wide Web"
        assert organizer.sales_channels.get(identifier="web").position == 9000


@pytest.mark.django_db
def test_channel_patch_invalid(token_client, organizer):
    resp = token_client.patch(
        '/api/v1/organizers/{}/saleschannels/web/'.format(organizer.slug),
        format='json',
        data={
            'identifier': 'foobar',
        }
    )
    assert resp.status_code == 400
    assert resp.data == {"identifier": ["You cannot change the identifier of a sales channel."]}

    resp = token_client.patch(
        '/api/v1/organizers/{}/saleschannels/web/'.format(organizer.slug),
        format='json',
        data={
            'type': 'foobar',
        }
    )
    assert resp.status_code == 400
    assert resp.data == {"type": ["You cannot change the type of a sales channel."]}


@pytest.mark.django_db
def test_channel_delete(token_client, organizer):
    with scopes_disabled():
        organizer.sales_channels.create(identifier="api.1", type="api", label="api")
    resp = token_client.delete(
        '/api/v1/organizers/{}/saleschannels/api.1/'.format(organizer.slug),
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert not organizer.sales_channels.filter(identifier="api.1").exists()


@pytest.mark.django_db
def test_channel_delete_invalid(token_client, organizer):
    resp = token_client.delete(
        '/api/v1/organizers/{}/saleschannels/web/'.format(organizer.slug),
    )
    assert resp.status_code == 403
    with scopes_disabled():
        assert organizer.sales_channels.filter(identifier="web").exists()
