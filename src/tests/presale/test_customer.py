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
from urllib.parse import parse_qs, quote, urlparse

import pytest
import responses
from django.core import mail as djmail, signing
from django.core.signing import dumps
from django.test import Client
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Customer, Event, Item, Order, OrderPosition, Organizer,
)
from pretix.base.models.customers import CustomerSSOProvider
from pretix.multidomain.models import KnownDomain
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
def test_native_disabled(env, client):
    env[0].settings.customer_accounts_native = False
    r = client.get('/bigevents/account/register')
    assert r.status_code == 404
    r = client.get('/bigevents/account/login')
    assert r.status_code == 200
    r = client.get('/bigevents/account/pwreset')
    assert r.status_code == 404
    r = client.get('/bigevents/account/pwrecover')
    assert r.status_code == 404
    r = client.get('/bigevents/account/activate')
    assert r.status_code == 404
    r = client.get('/bigevents/account/change')
    assert r.status_code == 302
    r = client.get('/bigevents/account/confirmchange')
    assert r.status_code == 302
    r = client.get('/bigevents/account/')
    assert r.status_code == 302


@pytest.mark.django_db
def test_org_register(env, client, mocker):
    from pretix.base.signals import customer_created
    mocker.patch('pretix.base.signals.customer_created.send')

    signer = signing.TimestampSigner(salt='customer-registration-captcha-127.0.0.1')

    r = client.post('/bigevents/account/register', {
        'email': 'john@example.org',
        'name_parts_0': 'John Doe',
        'challenge': signer.sign('1+2'),
        'response': '3',
    }, REMOTE_ADDR='127.0.0.1')
    assert r.status_code == 302
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        customer = env[0].customers.get(email='john@example.org')
        assert not customer.is_verified
        assert customer.is_active
        customer_created.send.assert_called_once_with(customer.organizer, customer=customer)

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
def test_org_register_duplicate_email(env, client, mocker):
    from pretix.base.signals import customer_created
    mocker.patch('pretix.base.signals.customer_created.send')

    with scopes_disabled():
        env[0].customers.create(email='john@example.org')
    r = client.post('/bigevents/account/register', {
        'email': 'john@example.org',
        'name_parts_0': 'John Doe',
    })
    assert b'already registered' in r.content
    assert r.status_code == 200
    customer_created.send.assert_not_called()


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
def test_org_login_logout(env, client, mocker):
    from pretix.base.signals import customer_signed_in
    mocker.patch('pretix.base.signals.customer_signed_in.send')

    customer = None
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 302

    customer_signed_in.send.assert_called_once_with(customer.organizer, customer=customer)

    r = client.get('/bigevents/account/')
    assert r.status_code == 200

    r = client.get('/bigevents/account/logout')
    assert r.status_code == 302

    r = client.get('/bigevents/account/')
    assert r.status_code == 302


@pytest.mark.django_db
def test_org_login_invalid_password(env, client, mocker):
    from pretix.base.signals import customer_signed_in
    mocker.patch('pretix.base.signals.customer_signed_in.send')

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
    customer_signed_in.send.assert_not_called()


@pytest.mark.django_db
def test_org_login_not_verified(env, client, mocker):
    from pretix.base.signals import customer_signed_in
    mocker.patch('pretix.base.signals.customer_signed_in.send')

    customer = None
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
    customer_signed_in.send.assert_not_called()


@pytest.mark.django_db
def test_org_login_not_active(env, client, mocker):
    from pretix.base.signals import customer_signed_in
    mocker.patch('pretix.base.signals.customer_signed_in.send')

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
    customer_signed_in.send.assert_not_called()


@pytest.fixture
def provider(env):
    return CustomerSSOProvider.objects.create(
        organizer=env[0],
        method="oidc",
        name="OIDC OP",
        configuration={
            "base_url": "https://example.com/provider",
            "client_id": "abc123",
            "client_secret": "abcdefghi",
            "uid_field": "sub",
            "email_field": "email",
            "scope": "openid email profile",
            "provider_config": {
                "authorization_endpoint": "https://example.com/authorize",
                "token_endpoint": "https://example.com/token",
                "userinfo_endpoint": "https://example.com/userinfo",
                "response_types_supported": ["code"],
                "response_modes_supported": ["query"],
                "grant_types_supported": ["authorization_code"],
                "scopes_supported": ["openid", "email", "profile"],
                "claims_supported": ["email", "sub"]
            }
        }
    )


@responses.activate
def _sso_login(client, provider, email='test@example.org', popup_origin=None, expect_fail=False):
    responses.reset()
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={
            'access_token': 'test_access_token',
        },
    )
    responses.add(
        responses.GET,
        "https://example.com/userinfo",
        json={
            'sub': 'abcdf',
            'email': email
        },
    )

    url = f'/bigevents/account/login/{provider.pk}/?next=/redirect'
    if popup_origin:
        url += '&popup_origin=' + popup_origin
    r = client.get(url, follow=False)
    assert r.status_code == 302
    assert "/authorize" in r['Location']
    u = urlparse(r['Location'])
    state = parse_qs(u.query)['state'][0]
    r = client.get(f'/bigevents/account/login/{provider.pk}/return?code=test_code&state={quote(state)}')
    if not expect_fail:
        if popup_origin:
            assert r.status_code == 200
            assert popup_origin in r.content.decode()
        else:
            assert r.status_code == 302
            assert "/redirect" in r['Location']
    else:
        if popup_origin:
            assert r.status_code == 200
            assert popup_origin in r.content.decode()
        else:
            assert r.status_code == 302
            assert "/account/login" in r['Location']

        r = client.get('/bigevents/account/')
        assert r.status_code == 302


@pytest.mark.django_db
def test_org_sso_login_new_customer(env, client, provider, mocker):
    from pretix.base.signals import customer_created, customer_signed_in
    mocker.patch('pretix.base.signals.customer_created.send')
    mocker.patch('pretix.base.signals.customer_signed_in.send')

    _sso_login(client, provider)

    with scopes_disabled():
        c = Customer.objects.get(provider=provider)
        assert c.external_identifier == "abcdf"
        customer_created.send.assert_called_once_with(c.organizer, customer=c)
        customer_signed_in.send.assert_called_once_with(c.organizer, customer=c)

    r = client.get('/bigevents/account/')
    assert r.status_code == 200


@pytest.mark.django_db
def test_org_sso_logout_if_provider_disabled(env, client, provider):
    _sso_login(client, provider)

    with scopes_disabled():
        c = Customer.objects.get(provider=provider)
        assert c.external_identifier == "abcdf"

    r = client.get('/bigevents/account/')
    assert r.status_code == 200

    provider.is_active = False
    provider.save()

    r = client.get('/bigevents/account/')
    assert r.status_code == 302


@pytest.mark.django_db
def test_org_sso_login_new_customer_popup(env, client, provider):
    KnownDomain.objects.create(organizer=env[0], event=env[1], domainname="popuporigin")
    _sso_login(client, provider, popup_origin="https://popuporigin")


@pytest.mark.django_db
def test_org_sso_login_new_customer_popup_invalid_origin(env, client, provider):
    KnownDomain.objects.create(organizer=env[0], event=env[1], domainname="popuporigin")
    with pytest.raises(AssertionError):
        _sso_login(client, provider, popup_origin="https://forbidden")


@pytest.mark.django_db
def test_org_sso_login_returning_customer_new_email(env, client, provider, mocker):
    from pretix.base.signals import customer_signed_in
    mocker.patch('pretix.base.signals.customer_signed_in.send')

    _sso_login(client, provider)
    with scopes_disabled():
        c = Customer.objects.get(provider=provider)
        customer_signed_in.send.assert_called_once_with(c.organizer, customer=c)
        customer_signed_in.send.reset_mock()

    r = client.get('/bigevents/account/logout')
    assert r.status_code == 302

    _sso_login(client, provider, 'new@example.net')
    c.refresh_from_db()
    assert c.email == "new@example.net"
    customer_signed_in.send.assert_called_once_with(c.organizer, customer=c)


@pytest.mark.django_db(transaction=True)
def test_org_sso_login_returning_customer_new_email_conflict(env, client, provider):
    with scopes_disabled():
        customer = env[0].customers.create(email='new@example.net', is_verified=True, is_active=False)
        customer.set_password('foo')
        customer.save()

    _sso_login(client, provider)

    r = client.get('/bigevents/account/logout')
    assert r.status_code == 302

    _sso_login(client, provider, 'new@example.net', expect_fail=True)


@pytest.mark.django_db(transaction=True)
def test_org_sso_login_new_customer_email_conflict(env, client, provider):
    with scopes_disabled():
        customer = env[0].customers.create(email='new@example.net', is_verified=True, is_active=False)
        customer.set_password('foo')
        customer.save()

    _sso_login(client, provider, 'new@example.net', expect_fail=True)


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

    r = client.get('/bigevents/account/')
    assert r.status_code == 200
    content = r.content.decode()
    assert o1.code not in content
    assert o2.code not in content
    assert o3.code in content

    env[0].settings.customer_accounts_link_by_email = True

    r = client.get('/bigevents/account/')
    assert r.status_code == 200
    content = r.content.decode()
    assert o1.code not in content
    assert o2.code in content
    assert o3.code in content


@pytest.mark.django_db
def test_no_login_for_sso_accounts_even_if_password_is_set(env, client, provider):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True, provider=provider)
        customer.set_password('foo')
        customer.save()

    r = client.post('/bigevents/account/login', {
        'email': 'john@example.org',
        'password': 'foo',
    })
    assert r.status_code == 200


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

    r = client.post('/bigevents/account/change', {
        'name_parts_0': 'John Doe',
        'email': 'john@example.org',
    })
    assert r.status_code == 302
    customer.refresh_from_db()
    assert customer.name == 'John Doe'


@pytest.mark.django_db
def test_no_change_email_or_pass_for_sso_customers(env, client, provider):
    _sso_login(client, provider, 'john@example.org')
    r = client.post('/bigevents/account/change', {
        'name_parts_0': 'Johnny',
        'email': 'john@example.com',
    })
    assert r.status_code == 302
    with scopes_disabled():
        customer = Customer.objects.get(provider=provider)
    customer.refresh_from_db()
    assert customer.email == 'john@example.org'
    assert customer.name == 'Johnny'
    assert len(djmail.outbox) == 0
    r = client.get('/bigevents/account/password')
    assert r.status_code == 404


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

    r = client.post('/bigevents/account/change', {
        'name_parts_0': 'John Doe',
        'email': 'john@example.com'
    })
    assert r.status_code == 200
    customer.refresh_from_db()
    assert customer.email == 'john@example.org'

    r = client.post('/bigevents/account/change', {
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

    r = client.post('/bigevents/account/password', {
        'password_current': 'invalid',
        'password': 'aYLBRNg4',
        'password_repeat': 'aYLBRNg4',
    })
    assert r.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password('foo')

    r = client.post('/bigevents/account/password', {
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


@pytest.fixture
def client2():
    # We need a second test client instance for cross domain stuff since the test client
    # does not isolate sessions per-domain like browsers do
    return Client()


def _cross_domain_login(env, client, client2):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()
        KnownDomain.objects.create(domainname='org.test', organizer=env[0])
        KnownDomain.objects.create(domainname='event.test', organizer=env[0], event=env[1])

    # Log in on org domain
    r = client.post('/account/login?next=https://event.test/redeem&request_cross_domain_customer_auth=true', {
        'email': 'john@example.org',
        'password': 'foo',
    }, HTTP_HOST='org.test')
    assert r.status_code == 302

    u = urlparse(r.headers['Location'])
    assert u.netloc == 'event.test'
    assert u.path == '/redeem'
    q = parse_qs(u.query)
    assert 'cross_domain_customer_auth' in q

    # Take session over to event domain
    r = client2.get(f'/?{u.query}', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content


@pytest.mark.django_db
def test_cross_domain_login(env, client, client2):
    _cross_domain_login(env, client, client2)

    # Logged in on org domain
    r = client.get('/', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content

    # Logged in on event domain
    r = client2.get('/', HTTP_HOST='org.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content


@pytest.mark.django_db
def test_cross_domain_logout_on_org_domain(env, client, client2):
    _cross_domain_login(env, client, client2)

    r = client.get('/account/logout', HTTP_HOST='org.test')
    assert r.status_code == 302

    # Logged out on org domain
    r = client.get('/', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' not in r.content

    # Logged out on event domain
    r = client2.get('/', HTTP_HOST='org.test')
    assert r.status_code == 200
    assert b'john@example.org' not in r.content


@pytest.mark.django_db
def test_cross_domain_logout_on_event_domain(env, client, client2):
    _cross_domain_login(env, client, client2)

    r = client2.get('/account/logout?next=/redeem', HTTP_HOST='event.test')
    assert r.status_code == 302

    u = urlparse(r.headers['Location'])
    assert u.netloc == 'org.test'
    assert u.path == '/account/logout'

    r = client.get(f'{u.path}?{u.query}', HTTP_HOST='org.test')
    assert r.status_code == 302
    assert r.headers['Location'] == 'http://event.test/redeem'

    # Logged out on org domain
    r = client.get('/', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' not in r.content

    # Logged out on event domain
    r = client2.get('/', HTTP_HOST='org.test')
    assert r.status_code == 200
    assert b'john@example.org' not in r.content


@pytest.mark.django_db
def test_cross_domain_login_otp_only_valid_once(env, client, client2):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()
        KnownDomain.objects.create(domainname='org.test', organizer=env[0])
        KnownDomain.objects.create(domainname='event.test', organizer=env[0], event=env[1])

    # Log in on org domain
    r = client.post('/account/login?next=https://event.test/redeem&request_cross_domain_customer_auth=true', {
        'email': 'john@example.org',
        'password': 'foo',
    }, HTTP_HOST='org.test')
    assert r.status_code == 302

    u = urlparse(r.headers['Location'])
    assert u.netloc == 'event.test'
    assert u.path == '/redeem'
    q = parse_qs(u.query)
    assert 'cross_domain_customer_auth' in q

    # Take session over to event domain
    r = client.get(f'/?{u.query}', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content

    # Try to use again
    r = client2.get(f'/?{u.query}', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' not in r.content


@pytest.mark.django_db
def test_cross_domain_login_validate_redirect_url(env, client, client2):
    with scopes_disabled():
        customer = env[0].customers.create(email='john@example.org', is_verified=True)
        customer.set_password('foo')
        customer.save()
        KnownDomain.objects.create(domainname='org.test', organizer=env[0])
        KnownDomain.objects.create(domainname='event.test', organizer=env[0], event=env[1])

    # Log in on org domain
    r = client.post('/account/login?next=https://evilcorp.test/redeem&request_cross_domain_customer_auth=true', {
        'email': 'john@example.org',
        'password': 'foo',
    }, HTTP_HOST='org.test')
    assert r.status_code == 302

    u = urlparse(r.headers['Location'])
    assert u.netloc == 'org.test'
    assert u.path == '/account/'
    q = parse_qs(u.query)
    assert 'cross_domain_customer_auth' not in q


@pytest.mark.django_db
@responses.activate
def test_cross_domain_login_with_sso(env, client, client2, provider):
    with scopes_disabled():
        KnownDomain.objects.create(domainname='org.test', organizer=env[0])
        KnownDomain.objects.create(domainname='event.test', organizer=env[0], event=env[1])

    # Log in on org domain
    responses.reset()
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={
            'access_token': 'test_access_token',
        },
    )
    responses.add(
        responses.GET,
        "https://example.com/userinfo",
        json={
            'sub': 'abcdf',
            'email': 'john@example.org'
        },
    )

    url = f'/account/login/{provider.pk}/?next=https://event.test/redeem&request_cross_domain_customer_auth=true'
    r = client.get(url, follow=False, HTTP_HOST='org.test')
    assert r.status_code == 302
    assert "/authorize" in r['Location']
    u = urlparse(r['Location'])
    state = parse_qs(u.query)['state'][0]

    r = client.get(f'/account/login/{provider.pk}/return?code=test_code&state={quote(state)}', HTTP_HOST='org.test')
    assert r.status_code == 302
    u = urlparse(r.headers['Location'])
    assert u.netloc == 'event.test'
    assert u.path == '/redeem'
    q = parse_qs(u.query)
    assert 'cross_domain_customer_auth' in q

    # Take session over to event domain
    r = client2.get(f'/?{u.query}', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content

    # Logged in on org domain
    r = client.get('/', HTTP_HOST='event.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content

    # Logged in on event domain
    r = client2.get('/', HTTP_HOST='org.test')
    assert r.status_code == 200
    assert b'john@example.org' in r.content
