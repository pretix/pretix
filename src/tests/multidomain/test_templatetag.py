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
from django.conf import settings
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
    settings.SITE_URL = 'http://example.com'
    event.get_cache().clear()
    return o, event


TEMPLATE_FRONT_PAGE = Template("{% load eventurl %} {% eventurl event 'presale:event.index' %}")
TEMPLATE_KWARGS = Template("{% load eventurl %} {% eventurl event 'presale:event.checkout' step='payment' %}")


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
