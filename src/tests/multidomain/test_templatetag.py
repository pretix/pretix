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
import pytest
from django.template import Context, Template, TemplateSyntaxError
from django.urls import NoReverseMatch
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.multidomain.models import KnownDomain


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now()
    )
    event.get_cache().clear()
    return o, event


TEMPLATE_FRONT_PAGE = Template("{% load eventurl %} {% eventurl event 'presale:event.index' %}")
TEMPLATE_KWARGS = Template("{% load eventurl %} {% eventurl event 'presale:event.checkout' step='payment' %}")
TEMPLATE_ABSEVENTURL = Template("{% load eventurl %} {% abseventurl event 'presale:event.checkout' step='payment' %}")
TEMPLATE_ABSMAINURL = Template("{% load eventurl %} {% absmainurl 'control:event.settings' organizer=event.organizer.slug event=event.slug %}")


@pytest.mark.django_db
def test_event_main_domain_front_page(env):
    rendered = TEMPLATE_FRONT_PAGE.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == '/mrmcd/2015/'


@pytest.mark.django_db
def test_event_custom_domain_front_page(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    rendered = TEMPLATE_FRONT_PAGE.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://foobar/2015/'


@pytest.mark.django_db
def test_event_custom_event_domain_front_page(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0], event=env[1], mode=KnownDomain.MODE_EVENT_DOMAIN)
    rendered = TEMPLATE_FRONT_PAGE.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://foobar/'


@pytest.mark.django_db
def test_event_custom_org_alt_domain_front_page(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0], mode=KnownDomain.MODE_ORG_DOMAIN)
    d = KnownDomain.objects.create(domainname='altfoo', organizer=env[0], mode=KnownDomain.MODE_ORG_ALT_DOMAIN)
    d.event_assignments.create(event=env[1])
    rendered = TEMPLATE_FRONT_PAGE.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://altfoo/2015/'


@pytest.mark.django_db
def test_event_custom_org_alt_domain_unassigned_front_page(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0], mode=KnownDomain.MODE_ORG_DOMAIN)
    KnownDomain.objects.create(domainname='altfoo', organizer=env[0], mode=KnownDomain.MODE_ORG_ALT_DOMAIN)
    rendered = TEMPLATE_FRONT_PAGE.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://foobar/2015/'


@pytest.mark.django_db
def test_event_main_domain_kwargs(env):
    rendered = TEMPLATE_KWARGS.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == '/mrmcd/2015/checkout/payment/'


@pytest.mark.django_db
def test_event_custom_domain_kwargs(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    rendered = TEMPLATE_KWARGS.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://foobar/2015/checkout/payment/'


@pytest.mark.django_db
def test_abseventurl_event_main_domain(env):
    rendered = TEMPLATE_ABSEVENTURL.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://example.com/mrmcd/2015/checkout/payment/'


@pytest.mark.django_db
def test_abseventurl_event_custom_domain(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    rendered = TEMPLATE_ABSEVENTURL.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://foobar/2015/checkout/payment/'


@pytest.mark.django_db
def test_absmainurl_main_domain(env):
    rendered = TEMPLATE_ABSMAINURL.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://example.com/control/event/mrmcd/2015/settings/'


@pytest.mark.django_db
def test_absmainurl_custom_domain(env):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    rendered = TEMPLATE_ABSMAINURL.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == 'http://example.com/control/event/mrmcd/2015/settings/'


@pytest.mark.django_db
def test_only_kwargs(env):
    with pytest.raises(TemplateSyntaxError):
        Template("{% load eventurl %} {% eventurl event 'presale:event.checkout' step %}")


@pytest.mark.django_db
def test_invalid_url(env):
    tpl = Template("{% load eventurl %} {% eventurl event 'presale:event.foo' %}")
    with pytest.raises(NoReverseMatch):
        tpl.render(Context({
            'event': env[1]
        })).strip()


@pytest.mark.django_db
def test_without_event(env):
    with pytest.raises(TemplateSyntaxError):
        Template("{% load eventurl %} {% eventurl 'presale:event.index' %}")


@pytest.mark.django_db
def test_save_as(env):
    tpl = Template("{% load eventurl %} {% eventurl event 'presale:event.index' as u %}{{ u }}")
    rendered = tpl.render(Context({
        'event': env[1]
    })).strip()
    assert rendered == '/mrmcd/2015/'
