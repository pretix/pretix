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

from pretix.base.models import Gate


TEST_RES = {
    "id": 1,
    "name": "Entry",
    "identifier": "entry"
}


@pytest.mark.django_db
def test_gate_list(token_client, organizer, gate):
    res = dict(TEST_RES)

    resp = token_client.get('/api/v1/organizers/{}/gates/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_gate_detail(token_client, organizer, gate):
    res = dict(TEST_RES)
    resp = token_client.get('/api/v1/organizers/{}/gates/{}/'.format(organizer.slug, gate.id))
    assert resp.status_code == 200
    assert res == resp.data


TEST_GATE_CREATE_PAYLOAD = {
    "name": "Second entry",
    "identifier": "entry_2"
}


@pytest.mark.django_db
def test_gate_create(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/gates/'.format(organizer.slug),
        TEST_GATE_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        g = Gate.objects.get(id=resp.data['id'])
        assert g.name == TEST_GATE_CREATE_PAYLOAD.get('name')
        assert g.identifier == TEST_GATE_CREATE_PAYLOAD.get('identifier')


@pytest.mark.django_db
def test_gate_update(token_client, organizer, gate):
    resp = token_client.patch(
        '/api/v1/organizers/{}/gates/{}/'.format(organizer.slug, gate.id),
        {
            'name': 'Main entry'
        },
        format='json'
    )
    assert resp.status_code == 200
    gate.refresh_from_db()
    assert gate.name == 'Main entry'
    assert gate.identifier == TEST_RES.get('identifier')


@pytest.mark.django_db
def test_gate_delete(token_client, organizer, gate):
    resp = token_client.delete(
        '/api/v1/organizers/{}/gates/{}/'.format(organizer.slug, gate.id),
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert organizer.gates.count() == 0
