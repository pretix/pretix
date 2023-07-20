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
import pytest
from django_scopes import scopes_disabled


@pytest.fixture
def item_meta_property(event):
    return event.item_meta_properties.create(
        name="Color",
        default="Red",
        required=False,
        allowed_values="",  # internally, this is a string
    )


TEST_TYPE_RES = {
    "name": "Color",
    "default": "Red",
    "required": False,
    "allowed_values": [],  # the external representation is a list
}


@pytest.mark.django_db
def test_meta_property_list(token_client, organizer, event, item_meta_property):
    res = dict(TEST_TYPE_RES)

    resp = token_client.get('/api/v1/organizers/{}/events/{}/item_meta_properties/'
                            .format(organizer.slug, event.slug))
    assert resp.status_code == 200
    item_meta_property.refresh_from_db()
    res["id"] = item_meta_property.pk
    assert res in resp.data['results']
    assert len(resp.data['results']) == 2
    # there is another meta property created in conftest using the old way, we
    # should check it still works, so the result should contain 2 entries


@pytest.mark.django_db
def test_meta_property_detail(token_client, organizer, event, item_meta_property):
    res = TEST_TYPE_RES
    resp = token_client.get('/api/v1/organizers/{}/events/{}/item_meta_properties/{}/'
                            .format(organizer.slug, event.slug, item_meta_property.pk))
    assert resp.status_code == 200
    item_meta_property.refresh_from_db()
    res["id"] = item_meta_property.pk
    assert res == resp.data


@pytest.mark.django_db
def test_meta_property_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/item_meta_properties/'.format(organizer.slug, event.slug),
        format='json',
        data={
            "name": "Color",
            "default": "Red",
            "required": False,
            "allowed_values": ["Red", "Green", "Blue"]
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        item_meta_property = event.item_meta_properties.get(id=resp.data['id'])
        assert item_meta_property.name == "Color"
        assert item_meta_property.default == "Red"
        assert item_meta_property.allowed_values == "Red\nGreen\nBlue"
        assert not item_meta_property.required
        assert len(event.item_meta_properties.all()) == 2


@pytest.mark.django_db
def test_meta_property_patch(token_client, organizer, event, item_meta_property):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/item_meta_properties/{}/'
        .format(organizer.slug, event.slug, item_meta_property.pk),
        format='json',
        data={
            "required": True,
            "allowed_values": None,
        }
    )
    assert resp.status_code == 200
    item_meta_property.refresh_from_db()
    assert item_meta_property.required
    assert item_meta_property.allowed_values is None


@pytest.mark.django_db
def test_meta_property_delete(token_client, organizer, event, item_meta_property):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/item_meta_properties/{}/'
        .format(organizer.slug, event.slug, item_meta_property.pk),
    )
    assert resp.status_code == 204
    assert len(event.item_meta_properties.all()) == 1
