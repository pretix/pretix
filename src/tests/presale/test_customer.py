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
import datetime
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail as djmail
from django.core.signing import dumps
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Item, Order, OrderPosition, Organizer
from pretix.presale.forms.customer import TokenGenerator


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Big Events LLC', slug='bigevents')
    o.settings.customer_accounts = True
    event = Event.objects.create(
        organizer=o, name='Conference', slug='conf',
        date_from=now() + timedelta(days=10),
        live=True, is_public=False
    )
    return o, event


@pytest.mark.django_db
def test_disabled(env, client):
    env[0].settings.customer_accounts = False
    r = client.get('/bigevents/account/register')
    assert r.status_code == 404
    r = client.get('/bigevents/account/login')
    assert r.status_code == 404
    r = client.get('/bigevents/account/pwreset')
    assert r.status_code == 404
    r = client.get('/bigevents/account/pwrecover')
    assert r.status_code == 404
    r = client.get('/bigevents/account/activate')
    assert r.status_code == 404
    r = client.get('/bigevents/account/change')
    assert r.status_code == 404
    r = client.get('/bigevents/account/confirmchange')
    assert r.status_code == 404
    r = client.get('/bigevents/account/')
    assert r.status_code == 404


@pytest.mark.django_db
def test_org_register(env, client):
    r = client.post('/bigevents/account/register', {
        'email': 'john@example.org',
        'name_parts_0': 'John Doe',
    })
    assert r.status_code == 302
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        customer = env[0].customers.get(email='john@example.org')
        assert not customer.is_verified
        assert customer.is_active

    r = client.post(
        f'/bigevents/account/activate?id={customer.identifier}&token={TokenGenerator().make_token(customer)}', {
            'password': 'PANioMR62',
            'password_repeat': 'PANioMR62',
        })
    assert r.status_code == 302

    customer.refresh_from_db()
    assert customer.check_password('PANioMR62')
    assert customer.is_verified


@pytest.mark.django_db
def test_org_register_duplicate_email(env, client):
    with scopes_disabled():
        env[0].customers.create(email='john@example.org')
    r = client.post('/bigevents/account/register', {
        'email': 'john@example.org',
        'name_parts_0': 'John Doe',
    })
    assert b'already registered' in r.content
    assert r.status_code == 200


@pytest.mark.django_db
def test_org_resetpw(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=False)

    r = client.post('/bigevents/account/pwreset', {
        'email': 'john@example.org',
    })
    assert r.status_code == 302
    assert len(djmail.outbox) == 1

    r = client.post(
        f'/bigevents/account/pwrecover?id={customer.identifier}&token={TokenGenerator().make_token(customer)}', {
            'password': 'PANioMR62',
            'password_repeat': 'PANioMR62',
        })
    assert r.status_code == 302

    customer.refresh_from_db()
    assert customer.check_password('PANioMR62')
    assert customer.is_verified


@pytest.mark.django_db
def test_org_activate_invalid_token(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=False)
    r = client.get(
        f'/bigevents/account/activate?id={customer.identifier}&token=.invalid.{TokenGenerator().make_token(customer)}')
    assert r.status_code == 302


@pytest.mark.django_db
def test_org_login_logout(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    r = client.get(f'/bigevents/account/')
    assert r.status_code == 200

    r = client.get('/bigevents/account/logout')
    assert r.status_code == 302

    r = client.get(f'/bigevents/account/')
    assert r.status_code == 302


@pytest.mark.django_db
def test_org_login_invalid_password(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'invalid',
    })
    assert r.status_code == 200
    assert b'alert-danger' in r.content


@pytest.mark.django_db
def test_org_login_not_verified(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=False)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 200
    assert b'alert-danger' in r.content


@pytest.mark.django_db
def test_org_login_not_active(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True, is_active=False)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 200
    assert b'alert-danger' in r.content


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "account/change",
    "account/membership/1/",
    "account/",
])
def test_login_required(client, env, url):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    assert client.get('/bigevents/' + url).status_code == 302

    client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert client.get('/bigevents/' + url).status_code in (200, 404)


@pytest.mark.django_db
def test_org_order_list(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()
        event = env[1]
        ticket = Item.objects.create(event=event, name='Early-bird ticket', default_price=23, admission=True)
        o1 = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=event,
            email='admin@localhost',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
        )
        OrderPosition.objects.create(
            order=o1,
            item=ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )
        o2 = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=event,
            email='john@example.org',
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
        )
        OrderPosition.objects.create(
            order=o2,
            item=ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )
        o3 = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=event,
            email='admin@localhost',
            customer=customer,
            datetime=now() - datetime.timedelta(days=3),
            expires=now() + datetime.timedelta(days=11),
            total=Decimal("23"),
        )
        OrderPosition.objects.create(
            order=o3,
            item=ticket,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"}
        )

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    r = client.get(f'/bigevents/account/')
    assert r.status_code == 200
    content = r.content.decode()
    assert o1.code not in content
    assert o2.code not in content
    assert o3.code in content

    env[0].settings.customer_accounts_link_by_email = True

    r = client.get(f'/bigevents/account/')
    assert r.status_code == 200
    content = r.content.decode()
    assert o1.code not in content
    assert o2.code in content
    assert o3.code in content


@pytest.mark.django_db
def test_change_name(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    r = client.post(f'/bigevents/account/change', {
        'name_parts_0': 'John Doe',
        'email': 'john@example.org',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    assert customer.name == 'John Doe'


@pytest.mark.django_db
def test_change_email(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    r = client.post(f'/bigevents/account/change', {
        'name_parts_0': 'John Doe',
        'email': 'john@example.com'
    })
    assert r.status_code == 200
    customer.refresh_from_db()
    assert customer.email == 'john@example.org'

    r = client.post(f'/bigevents/account/change', {
        'name_parts_0': 'John Doe',
        'email': 'john@example.com',
        'password_current': 'foo',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    assert customer.email == 'john@example.org'
    assert len(djmail.outbox) == 1

    token = dumps({
        'customer': customer.pk,
        'email': 'john@example.com'
    }, salt='pretix.presale.views.customer.ChangeInformationView')
    r = client.get(f'/bigevents/account/confirmchange?token={token}')
    assert r.status_code == 302
    customer.refresh_from_db()
    assert customer.email == 'john@example.com'


@pytest.mark.django_db
def test_change_pw(env, client):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    r = client.post(f'/bigevents/account/password', {
        'password_current': 'invalid',
        'password': 'aYLBRNg4',
        'password_repeat': 'aYLBRNg4',
    })
    assert r.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password('foo')

    r = client.post(f'/bigevents/account/password', {
        'password_current': 'foo',
        'password': 'aYLBRNg4',
        'password_repeat': 'aYLBRNg4',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    assert customer.check_password('aYLBRNg4')


@pytest.mark.django_db
def test_login_per_org(env, client):
    with scopes_disabled():
        o2 = Organizer.objects.create(name='Demo', slug='demo')
        o2.settings.customer_accounts = True
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert client.get('/bigevents/account/').status_code == 200
    assert client.get('/demo/account/').status_code == 302
