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
from django.test import override_settings
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests import assert_num_queries

from pretix.base.models import Event, Organizer
from pretix.multidomain.models import KnownDomain
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now()
    )
    event.get_cache().clear()
    return o, event


@pytest.mark.django_db
def test_event_main_domain_front_page(env):
    assert eventreverse(env[1], 'presale:event.index') == '/mrmcd/2015/'
    assert eventreverse(env[0], 'presale:organizer.index') == '/mrmcd/'


@pytest.mark.django_db
def test_event_custom_domain_kwargs(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    assert eventreverse(env[1], 'presale:event.checkout', {'step': 'payment'}) == 'http://barfoo/checkout/payment/'


@pytest.mark.django_db
def test_event_org_domain_kwargs(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    assert eventreverse(env[1], 'presale:event.checkout', {'step': 'payment'}) == 'http://foobar/2015/checkout/payment/'


@pytest.mark.django_db
def test_event_main_domain_kwargs(env):
    assert eventreverse(env[1], 'presale:event.checkout', {'step': 'payment'}) == '/mrmcd/2015/checkout/payment/'


@pytest.mark.django_db
def test_event_org_domain_front_page(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    assert eventreverse(env[1], 'presale:event.index') == 'http://foobar/2015/'
    assert eventreverse(env[0], 'presale:organizer.index') == 'http://foobar/'


@pytest.mark.django_db
def test_event_custom_domain_front_page(env):
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    assert eventreverse(env[1], 'presale:event.index') == 'http://barfoo/'
    assert eventreverse(env[0], 'presale:organizer.index') == '/mrmcd/'


@pytest.mark.django_db
def test_event_custom_and_org_domain_front_page(env):
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    assert eventreverse(env[1], 'presale:event.index') == 'http://barfoo/'
    assert eventreverse(env[0], 'presale:organizer.index') == 'http://foobar/'


@pytest.mark.django_db
def test_event_org_domain_keep_port(env):
    with override_settings(SITE_URL='http://example.com:8081'):
        KnownDomain.objects.create(domainname='foobar', organizer=env[0])
        assert eventreverse(env[1], 'presale:event.index') == 'http://foobar:8081/2015/'


@pytest.mark.django_db
def test_event_org_domain_keep_scheme(env):
    with override_settings(SITE_URL='https://example.com'):
        KnownDomain.objects.create(domainname='foobar', organizer=env[0])
        assert eventreverse(env[1], 'presale:event.index') == 'https://foobar/2015/'


@pytest.mark.django_db
@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
def test_event_main_domain_cache(env):
    env[0].get_cache().clear()
    with assert_num_queries(1):
        eventreverse(env[1], 'presale:event.index')
    with assert_num_queries(0):
        eventreverse(env[1], 'presale:event.index')


@pytest.mark.django_db
@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
def test_event_org_domain_cache(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    env[0].get_cache().clear()
    with assert_num_queries(1):
        eventreverse(env[1], 'presale:event.index')
    with assert_num_queries(0):
        eventreverse(env[1], 'presale:event.index')


@pytest.mark.django_db
@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
def test_event_custom_domain_cache(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    env[0].get_cache().clear()
    with assert_num_queries(1):
        eventreverse(env[1], 'presale:event.index')
    with assert_num_queries(0):
        eventreverse(env[1], 'presale:event.index')


@pytest.mark.django_db
@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
@scopes_disabled()
def test_event_org_domain_cache_clear(env):
    kd = KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    env[0].cache.clear()
    with assert_num_queries(1):
        eventreverse(env[1], 'presale:event.index')
    kd.delete()
    with assert_num_queries(2):
        ev = Event.objects.get(pk=env[1].pk)
        assert ev.pk == env[1].pk
        assert ev.organizer == env[0]
    with assert_num_queries(1):
        eventreverse(ev, 'presale:event.index')


@pytest.mark.django_db
@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
@scopes_disabled()
def test_event_custom_domain_cache_clear(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    kd = KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    env[0].cache.clear()
    with assert_num_queries(1):
        eventreverse(env[1], 'presale:event.index')
    kd.delete()
    with assert_num_queries(2):
        ev = Event.objects.get(pk=env[1].pk)
        assert ev.pk == env[1].pk
        assert ev.organizer == env[0]
    with assert_num_queries(1):
        eventreverse(ev, 'presale:event.index')


@pytest.mark.django_db
def test_event_main_domain_absolute(env):
    assert build_absolute_uri(env[1], 'presale:event.index') == 'http://example.com/mrmcd/2015/'


@pytest.mark.django_db
def test_event_custom_domain_absolute(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    assert build_absolute_uri(env[1], 'presale:event.index') == 'http://barfoo/'


@pytest.mark.django_db
def test_event_org_domain_absolute(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    assert build_absolute_uri(env[1], 'presale:event.index') == 'http://foobar/2015/'
