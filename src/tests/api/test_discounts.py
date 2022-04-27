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

from pretix.base.models import Discount


@pytest.fixture
def discount(event):
    return event.discounts.create(
        internal_name="3 for 2",
        condition_min_count=3,
        benefit_discount_matching_percent=100,
        benefit_only_apply_to_cheapest_n_matches=1,
        position=1,
    )


TEST_DISCOUNT_RES = {
    "active": True,
    "internal_name": "3 for 2",
    "position": 1,
    "sales_channels": ["web"],
    "available_from": None,
    "available_until": None,
    "subevent_mode": "mixed",
    "condition_all_products": True,
    "condition_limit_products": [],
    "condition_apply_to_addons": True,
    "condition_ignore_voucher_discounted": False,
    "condition_min_count": 3,
    "condition_min_value": "0.00",
    "benefit_discount_matching_percent": "100.00",
    "benefit_only_apply_to_cheapest_n_matches": 1
}


@pytest.mark.django_db
def test_discount_list(token_client, organizer, event, team, discount):
    res = dict(TEST_DISCOUNT_RES)
    res["id"] = discount.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/discounts/?active=true'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']
    resp = token_client.get('/api/v1/organizers/{}/events/{}/discounts/?active=false'.format(
        organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_discount_detail(token_client, organizer, event, team, discount):
    res = dict(TEST_DISCOUNT_RES)
    res["id"] = discount.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/discounts/{}/'.format(organizer.slug, event.slug,
                                                                                   discount.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_discount_create(token_client, organizer, event, team):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug),
        {
            "active": True,
            "internal_name": "3 for 2",
            "position": 2,
            "sales_channels": ["web"],
            "available_from": None,
            "available_until": None,
            "subevent_mode": "mixed",
            "condition_all_products": True,
            "condition_limit_products": [],
            "condition_apply_to_addons": True,
            "condition_ignore_voucher_discounted": False,
            "condition_min_count": 3,
            "condition_min_value": "0.00",
            "benefit_discount_matching_percent": "100.00",
            "benefit_only_apply_to_cheapest_n_matches": 1
        },
        format='json'
    )
    assert resp.status_code == 201
    with scopes_disabled():
        d = Discount.objects.get(pk=resp.data['id'])
        assert d.event == event
        assert d.internal_name == "3 for 2"


@pytest.mark.django_db
def test_discount_update(token_client, organizer, event, team, discount):
    resp = token_client.patch(
        '/api/v1/organizers/{}/events/{}/discounts/{}/'.format(organizer.slug, event.slug, discount.pk),
        {
            "internal_name": "Foo"
        },
        format='json'
    )
    assert resp.status_code == 200
    with scopes_disabled():
        d = Discount.objects.get(pk=resp.data['id'])
        assert d.event == event
        assert d.internal_name == "Foo"


@pytest.mark.django_db
def test_discount_delete(token_client, organizer, event, discount):
    resp = token_client.delete(
        '/api/v1/organizers/{}/events/{}/discounts/{}/'.format(organizer.slug, event.slug, discount.pk))
    assert resp.status_code == 204
    with scopes_disabled():
        assert not event.discounts.filter(pk=discount.id).exists()


@pytest.mark.django_db
def test_validate_errors(token_client, organizer, event, team):
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug),
        {
            "internal_name": "3 for 2",
            "subevent_mode": "mixed",
            "condition_min_count": 3,
            "condition_min_value": "2.00",
            "benefit_discount_matching_percent": "100.00",
            "benefit_only_apply_to_cheapest_n_matches": 1
        },
        format='json'
    )
    assert resp.status_code == 400

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug),
        {
            "internal_name": "3 for 2",
            "subevent_mode": "mixed",
            "condition_min_count": 0,
            "condition_min_value": "0.00",
            "benefit_discount_matching_percent": "100.00",
            "benefit_only_apply_to_cheapest_n_matches": 1
        },
        format='json'
    )
    assert resp.status_code == 400

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug),
        {
            "internal_name": "3 for 2",
            "subevent_mode": "mixed",
            "condition_min_count": 0,
            "condition_min_value": "2.00",
            "benefit_discount_matching_percent": "100.00",
            "benefit_only_apply_to_cheapest_n_matches": 1
        },
        format='json'
    )
    assert resp.status_code == 400

    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/discounts/'.format(organizer.slug, event.slug),
        {
            "internal_name": "3 for 2",
            "subevent_mode": "distinct",
            "condition_min_count": 0,
            "condition_min_value": "2.00",
            "benefit_discount_matching_percent": "100.00",
        },
        format='json'
    )
    assert resp.status_code == 400
