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
from django.core import mail as djmail
from django_scopes import scopes_disabled


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
    "external_identifier": None,
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
    "last_modified": "2021-04-06T13:44:22.809377Z",
    "notes": None,
}


@pytest.mark.django_db
def test_customer_list(token_client, organizer, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')

    resp = token_client.get('/api/v1/organizers/{}/customers/'.format(organizer.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_customer_detail(token_client, organizer, customer):
    res = dict(TEST_CUSTOMER_RES)
    res["date_joined"] = customer.date_joined.isoformat().replace('+00:00', 'Z')
    res["last_modified"] = customer.last_modified.isoformat().replace('+00:00', 'Z')
    resp = token_client.get('/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_customer_create(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/customers/'.format(organizer.slug),
        format='json',
        data={
            'identifier': 'IGNORED',
            'email': 'bar@example.com',
            'password': 'foobar',
            'name_parts': {
                "_scheme": "given_family",
                'given_name': 'John',
                'family_name': 'Doe',
            },
            'is_active': True,
            'is_verified': True,
        }
    )
    assert resp.status_code == 201
    with scopes_disabled():
        customer = organizer.customers.get(identifier=resp.data['identifier'])
        assert customer.identifier != 'IGNORED'
        assert customer.email == 'bar@example.com'
        assert customer.is_active
        assert customer.name == 'John Doe'
        assert customer.is_verified
        assert customer.check_password('foobar')
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_customer_create_send_email(token_client, organizer):
    resp = token_client.post(
        '/api/v1/organizers/{}/customers/'.format(organizer.slug),
        format='json',
        data={
            'identifier': 'IGNORED',
            'email': 'bar@example.com',
            'name_parts': {
                "_scheme": "given_family",
                'given_name': 'John',
                'family_name': 'Doe',
            },
            'is_active': True,
            'is_verified': True,
            'send_email': True,
        }
    )
    assert resp.status_code == 201
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_customer_patch(token_client, organizer, customer):
    resp = token_client.patch(
        '/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier),
        format='json',
        data={
            'email': 'blubb@example.org',
        }
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert customer.email == 'blubb@example.org'


@pytest.mark.django_db
def test_customer_patch_with_provider(token_client, organizer, customer):
    with scopes_disabled():
        customer.provider = organizer.sso_providers.create(
            method="oidc",
            name="OIDC OP",
            configuration={}
        )
        customer.external_identifier = "123"
        customer.save()

    resp = token_client.patch(
        '/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier),
        format='json',
        data={
            'external_identifier': '234',
        }
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert customer.external_identifier == "123"


@pytest.mark.django_db
def test_customer_anonymize(token_client, organizer, customer):
    resp = token_client.post(
        '/api/v1/organizers/{}/customers/{}/anonymize/'.format(organizer.slug, customer.identifier),
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert customer.email is None


@pytest.mark.django_db
def test_customer_delete(token_client, organizer, customer):
    resp = token_client.delete(
        '/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier),
    )
    assert resp.status_code == 405


@pytest.mark.django_db
def test_customer_patch_invalid_name(token_client, organizer, customer):
    resp = token_client.patch(
        '/api/v1/organizers/{}/customers/{}/'.format(organizer.slug, customer.identifier),
        format='json',
        data={
            'name_parts': 'should be a dictionary',
        }
    )
    assert resp.status_code == 400
