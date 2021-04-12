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
from django_scopes import scopes_disabled

from pretix.base.models import SeatingPlan

SAMPLE_PLAN = """{
  "name": "Sample plan",
  "categories": [
    {
      "name": "Stalls",
      "color": "#33ffff"
    }
  ],
  "zones": [
    {
      "name": "Main Area",
      "position": {
        "x": 0,
        "y": 0
      },
      "rows": [
        {
          "row_number": "0",
          "seats": [
            {
              "seat_guid": "0-0",
              "seat_number": "0-0",
              "position": {
                "x": 0,
                "y": 0
              },
              "category": "Stalls"
            },
            {
              "seat_guid": "0-1",
              "seat_number": "0-1",
              "position": {
                "x": 30,
                "y": 0
              },
              "category": "Stalls"
            }
          ],
          "position": {
            "x": 40,
            "y": 25
          }
        }
      ]
    }
  ],
  "size": {
    "width": 600,
    "height": 500
  }
}"""


@pytest.fixture
def seatingplan(organizer, event):
    wh = organizer.seating_plans.create(
        name="Plan",
        layout=SAMPLE_PLAN
    )
    return wh


TEST_PLAN_RES = {
    "id": 1,
    "name": "Plan",
    "layout": json.loads(SAMPLE_PLAN)
}


@pytest.mark.django_db
def test_plan_list(token_client, organizer, event, seatingplan):
    res = dict(TEST_PLAN_RES)
    res["id"] = seatingplan.pk

    resp = token_client.get('/api/v1/organizers/{}/seatingplans/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_plan_detail(token_client, organizer, event, seatingplan):
    res = dict(TEST_PLAN_RES)
    res["id"] = seatingplan.pk
    resp = token_client.get('/api/v1/organizers/{}/seatingplans/{}/'.format(organizer.slug, seatingplan.pk))
    assert resp.status_code == 200
    assert res == resp.data


TEST_PLAN_CREATE_PAYLOAD = {
    "name": "Plan 2",
    "layout": json.loads(SAMPLE_PLAN)
}


@pytest.mark.django_db
def test_plan_create(token_client, organizer, event):
    resp = token_client.post(
        '/api/v1/organizers/{}/seatingplans/'.format(organizer.slug),
        TEST_PLAN_CREATE_PAYLOAD,
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        cl = SeatingPlan.objects.get(pk=resp.data['id'])
        assert json.loads(cl.layout) == TEST_PLAN_CREATE_PAYLOAD['layout']


@pytest.mark.django_db
def test_plan_create_invalid_layout(token_client, organizer, event):
    res = copy.copy(TEST_PLAN_CREATE_PAYLOAD)
    res['layout'] = {'foo': 'bar'}
    resp = token_client.post(
        '/api/v1/organizers/{}/seatingplans/'.format(organizer.slug),
        res,
        format='json'
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_plan_patch(token_client, organizer, event, seatingplan):
    resp = token_client.patch(
        '/api/v1/organizers/{}/seatingplans/{}/'.format(organizer.slug, seatingplan.pk),
        {
            'name': 'Foo'
        },
        format='json'
    )
    assert resp.status_code == 200
    seatingplan.refresh_from_db()
    assert seatingplan.name == "Foo"


@pytest.mark.django_db
def test_plan_delete(token_client, organizer, event, seatingplan):
    resp = token_client.delete(
        '/api/v1/organizers/{}/seatingplans/{}/'.format(organizer.slug, seatingplan.pk),
    )
    assert resp.status_code == 204
    with scopes_disabled():
        assert SeatingPlan.objects.count() == 0


@pytest.mark.django_db
def test_plan_patch_used(token_client, organizer, event, seatingplan):
    event.seating_plan = seatingplan
    event.save()
    resp = token_client.patch(
        '/api/v1/organizers/{}/seatingplans/{}/'.format(organizer.slug, seatingplan.pk),
        {
            'name': 'Foo'
        },
        format='json'
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_plan_delete_used(token_client, organizer, event, seatingplan):
    event.seating_plan = seatingplan
    event.save()
    resp = token_client.delete(
        '/api/v1/organizers/{}/seatingplans/{}/'.format(organizer.slug, seatingplan.pk),
    )
    assert resp.status_code == 403
