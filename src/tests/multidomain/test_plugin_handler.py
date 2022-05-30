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
from django.utils.timezone import now

from pretix.base.models import Event, Organizer


@pytest.fixture
def event():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now(),
    )
    settings.SITE_URL = 'http://example.com'
    return event


@pytest.mark.django_db
def test_require_plugin(event, client):
    event.plugins = 'pretix.plugins.paypal'
    event.live = True
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 302
    event.plugins = ''
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 404


@pytest.mark.django_db
def test_require_live(event, client):
    event.plugins = 'pretix.plugins.paypal'
    event.live = True
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 302

    event.live = False
    event.save()
    r = client.get('/mrmcd/2015/paypal/abort/', follow=False)
    assert r.status_code == 403
