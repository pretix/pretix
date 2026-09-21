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


@pytest.fixture
def event_meta_property(organizer):
    return organizer.meta_properties.create(
        name="Color",
        default="Red",
        required=False,
        choices=[
            {
                "key": "Red",
                "label": "Rot",
                "DELETE": False,
                "ORDER": 1,
            }
        ],
    )


TEST_TYPE_RES = {
    "name": "Color",
    "default": "Red",
    "required": False,
    "choices": [{"key": "Red", "label": "Rot"}],
    'filter_allowed': True,
    'filter_public': False,
    'protected': False,
    'public_label': None,
}


@pytest.mark.django_db
def test_meta_property_list(token_client, organizer, event_meta_property):
    res = dict(TEST_TYPE_RES)

    resp = token_client.get('/api/v1/organizers/{}/event_meta_properties/'
                            .format(organizer.slug))
    assert resp.status_code == 200
    event_meta_property.refresh_from_db()
    res["id"] = event_meta_property.pk
    assert res in resp.data['results']
    assert len(resp.data['results']) == 1


@pytest.mark.django_db
def test_meta_property_detail(token_client, organizer, event_meta_property):
    res = TEST_TYPE_RES
    resp = token_client.get('/api/v1/organizers/{}/event_meta_properties/{}/'
                            .format(organizer.slug, event_meta_property.pk))
    assert resp.status_code == 200
    event_meta_property.refresh_from_db()
    res["id"] = event_meta_property.pk
    assert res == resp.data


@pytest.mark.django_db
def test_meta_property_create(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "Red",
            "required": False,
            "choices": ["Red", "Green", "Blue"]
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["choices"][0]) == "Choices need to contain only objects."

    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "Red",
            "required": False,
            "choices": {"key": "r", "label": "Red"},
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["choices"][0]) == "Choices need to be a list or null."

    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "r",
            "required": False,
            "choices": [
                {"key": "r", "label": "Red"},
                {"key": "r", "label": "Razzmatazz"},
            ],
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["choices"][0]) == "Each choice must have a unique key."

    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "r",
            "required": False,
            "choices": [
                {"key": "r", "label": "Red"},
                {"label": "Green"},
            ],
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["choices"][0]) == "Each choice must contain a key and optionally a label."

    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "r",
            "required": False,
            "choices": [
                {"key": "r", "label": "Red", "UNKNOWN_KEY": 1},
            ],
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["choices"][0]) == "Each choice must contain a key and optionally a label."

    choices = [
        {"key": "r", "label": "Red"},
        {"key": "g", "label": "Green"},
        {"key": "b", "label": "Blue"},
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "k",
            "required": False,
            "choices": choices,
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["non_field_errors"][0]) == "You cannot set a default value that is not a valid value."

    resp = token_client.post(
        '/api/v1/organizers/{}/event_meta_properties/'.format(organizer.slug),
        format='json',
        data={
            "name": "Color",
            "default": "r",
            "required": False,
            "choices": choices,
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        event_meta_property = organizer.meta_properties.get(id=resp.data['id'])
        assert event_meta_property.name == "Color"
        assert event_meta_property.default == "r"
        assert event_meta_property.choices == choices
        assert not event_meta_property.required
        assert len(organizer.meta_properties.all()) == 1


@pytest.mark.django_db
def test_meta_property_patch(token_client, organizer, event_meta_property):
    resp = token_client.patch(
        '/api/v1/organizers/{}/event_meta_properties/{}/'
        .format(organizer.slug, event_meta_property.pk),
        format='json',
        data={
            # existing default is not in choices
            "choices": [{'key': 'k', 'label': 'Black'}],
        }
    )
    assert resp.status_code == 400
    assert str(resp.data["non_field_errors"][0]) == "You cannot set a default value that is not a valid value."

    resp = token_client.patch(
        '/api/v1/organizers/{}/event_meta_properties/{}/'
        .format(organizer.slug, event_meta_property.pk),
        format='json',
        data={
            "choices": [],
        }
    )
    assert resp.status_code == 200
    event_meta_property.refresh_from_db()
    assert event_meta_property.choices is None

    resp = token_client.patch(
        '/api/v1/organizers/{}/event_meta_properties/{}/'
        .format(organizer.slug, event_meta_property.pk),
        format='json',
        data={
            "required": True,
            "choices": None,
        }
    )
    assert resp.status_code == 200
    event_meta_property.refresh_from_db()
    assert event_meta_property.required
    assert event_meta_property.choices is None


@pytest.mark.django_db
def test_meta_property_delete(token_client, organizer, event_meta_property):
    resp = token_client.delete(
        '/api/v1/organizers/{}/event_meta_properties/{}/'
        .format(organizer.slug, event_meta_property.pk),
    )
    assert resp.status_code == 204
    assert len(organizer.meta_properties.all()) == 0
