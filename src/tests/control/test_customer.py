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
from datetime import timedelta
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import extract_form_fields

from pretix.base.models import (
    Item, Order, OrderPosition, Organizer, Team, User,
)
from pretix.base.models.customers import CustomerSSOProvider


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def customer(organizer):
    return organizer.customers.create(email="john@example.org")


@pytest.fixture
def membership_type(organizer):
    return organizer.membership_types.create(name="Week pass")


@pytest.fixture
def event(organizer):
    return organizer.events.create(
        name='Conference', slug='conf',
        date_from=now() + timedelta(days=10),
        live=True, is_public=False
    )


@pytest.fixture
def order(event, customer):
    ticket = Item.objects.create(event=event, name='Early-bird ticket', default_price=23, admission=True)
    o1 = Order.objects.create(
        status=Order.STATUS_PENDING,
        event=event,
        customer=customer,
        email='admin@localhost',
        datetime=now() - timedelta(days=3),
        expires=now() + timedelta(days=11),
        total=Decimal("23"),
    )
    OrderPosition.objects.create(
        order=o1,
        item=ticket,
        variation=None,
        price=Decimal("23"),
        attendee_name_parts={'full_name': "Peter"}
    )
    return o1


@pytest.fixture
def admin_user(organizer):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team = Team.objects.create(
        organizer=organizer, can_manage_customers=True, can_change_organizer_settings=True,
        name='Admin team'
    )
    admin_team.members.add(u)
    return u


@pytest.fixture
def provider(organizer):
    return CustomerSSOProvider.objects.create(
        organizer=organizer,
        method="oidc",
        name="OIDC OP",
        configuration={}
    )


@pytest.mark.django_db
def test_list_of_customers(organizer, admin_user, client, customer):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/customers')
    assert customer.identifier in resp.content.decode()
    resp = client.get('/control/organizer/dummy/customers?query=john@example.org')
    assert customer.identifier in resp.content.decode()
    resp = client.get('/control/organizer/dummy/customers?query=1234_FOO')
    assert customer.identifier not in resp.content.decode()


@pytest.mark.django_db
def test_customer_detail_view(organizer, admin_user, customer, client, order):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/customer/{}/'.format(customer.identifier))
    c = resp.content.decode()
    assert customer.email in c
    assert order.code in c


@pytest.mark.django_db
def test_customer_update(organizer, admin_user, customer, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/customer/{}/edit'.format(customer.identifier))
    doc = BeautifulSoup(resp.content, "lxml")
    d = extract_form_fields(doc)
    d['name_parts_0'] = 'John Doe'
    d['is_verified'] = 'on'
    resp = client.post('/control/organizer/dummy/customer/{}/edit'.format(customer.identifier), d)
    assert resp.status_code == 302
    customer.refresh_from_db()
    assert customer.name == 'John Doe'
    assert customer.is_verified


@pytest.mark.django_db
def test_customer_update_email_not_allowed_for_sso_customers(organizer, admin_user, customer, client, provider):
    customer.provider = provider
    customer.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/customer/{}/edit'.format(customer.identifier))
    doc = BeautifulSoup(resp.content, "lxml")
    d = extract_form_fields(doc)
    d['name_parts_0'] = 'John Doe'
    d['email'] = 'customer@example.net'
    d['external_identifier'] = 'aaaaaaa'
    resp = client.post('/control/organizer/dummy/customer/{}/edit'.format(customer.identifier), d)
    assert resp.status_code == 302
    customer.refresh_from_db()
    assert customer.name == 'John Doe'
    assert customer.email == "john@example.org"
    assert not customer.external_identifier


@pytest.mark.django_db
def test_customer_anonymize(organizer, admin_user, customer, client, order):
    customer.is_active = True
    customer.name_parts = {'_legacy': 'Foo'}
    customer.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/customer/{}/anonymize'.format(customer.identifier))
    customer.refresh_from_db()
    order.refresh_from_db()
    assert not customer.name_parts
    assert not customer.name_cached
    assert not customer.email
    assert not customer.is_active
    assert not customer.is_verified
    assert not order.customer


@pytest.mark.django_db
def test_list_of_membership_types(organizer, admin_user, client, customer, membership_type):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/membershiptypes')
    c = resp.content.decode()
    assert 'Week pass' in c


@pytest.mark.django_db
def test_update_membership_type(organizer, admin_user, customer, client, membership_type):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/membershiptype/{}/edit'.format(membership_type.pk))
    doc = BeautifulSoup(resp.content, "lxml")
    d = extract_form_fields(doc)
    d['transferable'] = 'on'
    resp = client.post('/control/organizer/dummy/membershiptype/{}/edit'.format(membership_type.pk), d)
    assert resp.status_code == 302
    membership_type.refresh_from_db()
    assert membership_type.transferable


@pytest.mark.django_db
def test_add_membership_type(organizer, admin_user, customer, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/membershiptype/add', {
        'name_0': 'Year pass',
        'max_usages': '3'
    })
    assert resp.status_code == 302
    with scopes_disabled():
        mt = organizer.membership_types.get()
        assert str(mt.name) == 'Year pass'
        assert mt.max_usages == 3


@pytest.mark.django_db
def test_delete_membership_type(organizer, admin_user, customer, client, membership_type):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/membershiptype/{}/delete'.format(membership_type.pk))
    assert resp.status_code == 302
    with scopes_disabled():
        assert not organizer.membership_types.exists()


@pytest.mark.django_db
def test_delete_membership_type_forbidden(organizer, admin_user, customer, client, membership_type):
    client.login(email='dummy@dummy.dummy', password='dummy')
    with scopes_disabled():
        customer.memberships.create(customer=customer, date_start=now(), date_end=now(), membership_type=membership_type)
    resp = client.post('/control/organizer/dummy/membershiptype/{}/delete'.format(membership_type.pk))
    assert resp.status_code == 302
    with scopes_disabled():
        assert organizer.membership_types.exists()


@pytest.mark.django_db
def test_customer_add_and_change_membership(organizer, admin_user, customer, client, membership_type):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/customer/{}/membership/add'.format(customer.identifier), {
        'membership_type': membership_type.pk,
        'date_start_0': '2021-01-01',
        'date_start_1': '00:00:00',
        'date_end_0': '2021-01-08',
        'date_end_1': '23:59:59',
        'attendee_name_parts_0': 'John Doe',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    with scopes_disabled():
        m = customer.memberships.get()
        assert m.membership_type == membership_type
        assert m.date_start.isoformat().startswith('2021-01-01')
        assert m.date_end.isoformat().startswith('2021-01-08')
        assert m.attendee_name == 'John Doe'

    r = client.post('/control/organizer/dummy/customer/{}/membership/{}/edit'.format(customer.identifier, m.pk), {
        'membership_type': membership_type.pk,
        'date_start_0': '2021-01-02',
        'date_start_1': '00:00:00',
        'date_end_0': '2021-01-09',
        'date_end_1': '23:59:59',
        'attendee_name_parts_0': 'Maria Doe',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    with scopes_disabled():
        m = customer.memberships.get()
        assert m.membership_type == membership_type
        assert m.date_start.isoformat().startswith('2021-01-02')
        assert m.date_end.isoformat().startswith('2021-01-09')
        assert m.attendee_name == 'Maria Doe'
