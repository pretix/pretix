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


@pytest.fixture
def customer(organizer, event):
    return organizer.customers.create(
        identifier="8WSAJCJ",
        email="foo@example.org",
        name_parts={"_legacy": "Foo"},
        name_cached="Foo",
        is_verified=False,
    )


TEST_CUSTOMER_RES = {
    "identifier": "8WSAJCJ",
    "email": "foo@example.org",
    "name": "Foo",
    "name_parts": {
        "_legacy": "Foo",
    },
    "is_active": True,
    "is_verified": False,
    "last_login": None,
    "date_joined": "2021-04-06T13:44:22.809216Z",
    "locale": "en",
    "last_modified": "2021-04-06T13:44:22.809377Z"
}


@pytest.mark.django_db
def test_customer_list(token_client, organizer, event, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/customers/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_customer_detail(token_client, organizer, event, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier))
    assert resp.status_code == 200
    assert res == resp.data
