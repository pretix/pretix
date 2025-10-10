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
import copy

import pytest
from django_scopes import scopes_disabled


@pytest.fixture
def acr(event, item):
    acr = event.autocheckinrule_set.create(
        all_products=False,
    )
    acr.limit_products.add(item)
    return acr


RES_RULE = {
    "list": None,
    "mode": "placed",
    "all_sales_channels": True,
    "limit_sales_channels": [],
    "all_products": False,
    "limit_products": [],
    "limit_variations": [],
    "all_payment_methods": True,
    "limit_payment_methods": set(),
}


@pytest.mark.django_db
def test_api_list(event, acr, item, token_client):
    res = copy.copy(RES_RULE)
    res["id"] = acr.pk
    res["limit_products"] = [item.pk]
    r = token_client.get(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/".format(
            event.organizer.slug, event.slug
        )
    ).data

    assert r["results"] == [res]


@pytest.mark.django_db
def test_api_detail(event, acr, item, token_client):
    res = copy.copy(RES_RULE)
    res["id"] = acr.pk
    res["limit_products"] = [item.pk]
    r = token_client.get(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/{}/".format(
            event.organizer.slug, event.slug, acr.pk
        )
    ).data
    assert r == res


@pytest.mark.django_db
def test_api_create(event, acr, item, token_client):
    resp = token_client.post(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/".format(
            event.slug, event.slug
        ),
        {
            "all_products": False,
            "limit_products": [item.pk],
        },
        format="json",
    )
    assert resp.status_code == 201
    with scopes_disabled():
        acr = event.autocheckinrule_set.get(pk=resp.data["id"])
        assert list(acr.limit_products.all()) == [item]


@pytest.mark.django_db
def test_api_create_validate_pprov(event, acr, item, token_client):
    resp = token_client.post(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/".format(
            event.slug, event.slug
        ),
        {
            "mode": "placed",
            "all_payment_methods": False,
            "limit_payment_methods": ["manual"],
        },
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data == {
        "non_field_errors": ["all_payment_methods should be used for mode=placed"]
    }

    resp = token_client.post(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/".format(
            event.slug, event.slug
        ),
        {
            "mode": "paid",
            "all_payment_methods": False,
            "limit_payment_methods": ["unknown"],
        },
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data == {"limit_payment_methods": ['"unknown" is not a valid choice.']}


@pytest.mark.django_db
def test_api_update(event, acr, item, token_client):
    resp = token_client.patch(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/{}/".format(
            event.slug, event.slug, acr.pk
        ),
        {
            "mode": "paid",
            "all_payment_methods": False,
            "limit_payment_methods": ["manual"],
        },
        format="json",
    )
    assert resp.status_code == 200
    acr.refresh_from_db()
    assert acr.all_payment_methods is False
    assert acr.limit_payment_methods == ["manual"]


@pytest.mark.django_db
def test_api_delete(event, acr, item, token_client):
    resp = token_client.delete(
        "/api/v1/organizers/{}/events/{}/auto_checkin_rules/{}/".format(
            event.slug, event.slug, acr.pk
        ),
    )
    assert resp.status_code == 204
    assert not event.autocheckinrule_set.exists()
