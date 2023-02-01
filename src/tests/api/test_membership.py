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
from datetime import datetime, timezone

import pytest
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.models import Membership


@pytest.fixture
def membershiptype(organizer):
    return organizer.membership_types.create(
        name=LazyI18nString({"en": "Week pass"}),
        transferable=True,
        allow_parallel_usage=False,
        max_usages=15,
    )


@pytest.fixture
def customer(organizer):
    return organizer.customers.create(
        identifier="8WSAJCJ",
        email="foo@example.org",
        name_parts={"_legacy": "Foo"},
        name_cached="Foo",
        is_verified=False,
    )


@pytest.fixture
def membership(organizer, customer, membershiptype):
    return customer.memberships.create(
        membership_type=membershiptype,
        date_start=datetime(2021, 4, 1, 0, 0, 0, 0, tzinfo=timezone.utc),
        date_end=datetime(2021, 4, 8, 23, 59, 59, 999999, tzinfo=timezone.utc),
        attendee_name_parts={
            "_scheme": "given_family",
            'given_name': 'John',
            'family_name': 'Doe',
        }
    )


TEST_MEMBERSHIP_RES = {
    "customer": "8WSAJCJ",
    "date_start": "2021-04-01T00:00:00Z",
    "date_end": "2021-04-08T23:59:59.999999Z",
    "testmode": False,
    "attendee_name_parts": {
        "_scheme": "given_family",
        'given_name': 'John',
        'family_name': 'Doe',
    }
}


@pytest.mark.django_db
def test_membership_list(token_client, organizer, membershiptype, membership):
    res = dict(TEST_MEMBERSHIP_RES)
    res['membership_type'] = membershiptype.pk
    res['id'] = membership.pk

    resp = token_client.get('/api/v1/organizers/{}/memberships/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_membership_detail(token_client, organizer, membershiptype, membership):
    res = dict(TEST_MEMBERSHIP_RES)
    res['membership_type'] = membershiptype.pk
    res['id'] = membership.pk
    resp = token_client.get('/api/v1/organizers/{}/memberships/{}/'.format(organizer.slug, membership.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_membership_create(token_client, organizer, membershiptype, customer):
    resp = token_client.post(
        '/api/v1/organizers/{}/memberships/'.format(organizer.slug),
        format='json',
        data={
            "customer": customer.identifier,
            "membership_type": membershiptype.pk,
            "date_start": "2021-04-01T00:00:00.000Z",
            "date_end": "2021-04-08T23:59:59.999999Z",
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        membership = Membership.objects.get(id=resp.data['id'])
        assert membership.customer == customer
        assert membership.membership_type == membershiptype


@pytest.mark.django_db
def test_membership_patch(token_client, organizer, customer, membership):
    resp = token_client.patch(
        '/api/v1/organizers/{}/memberships/{}/'.format(organizer.slug, membership.pk),
        format='json',
        data={
            "date_end": "2021-04-03T23:59:59.999999Z",
        }
    )
    assert resp.status_code == 200
    membership.refresh_from_db()
    assert membership.date_end.isoformat() == "2021-04-03T23:59:59.999999+00:00"

    with scopes_disabled():
        other_customer = organizer.customers.create()
    resp = token_client.patch(
        '/api/v1/organizers/{}/memberships/{}/'.format(organizer.slug, membership.pk),
        format='json',
        data={
            "customer": other_customer.identifier,
            "testmode": True,
        }
    )
    assert resp.status_code == 200
    membership.refresh_from_db()
    assert membership.customer == customer  # change is ignored
    assert not membership.testmode  # change is ignored


@pytest.mark.django_db
def test_membership_delete(token_client, organizer, membership):
    resp = token_client.delete(
        '/api/v1/organizers/{}/memberships/{}/'.format(organizer.slug, membership.pk),
    )
    assert resp.status_code == 405
