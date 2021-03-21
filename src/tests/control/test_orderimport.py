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
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def env():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    t = Team.objects.create(organizer=event.organizer, can_view_orders=True, can_change_orders=True)
    t.members.add(user)
    t.limit_events.add(event)
    return event, user


@pytest.mark.django_db
def test_import_csv_file(client, env):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.get('/control/event/dummy/dummy/orders/import/')
    assert r.status_code == 200

    file = SimpleUploadedFile('file.csv', """First name,Last name,Email
Dieter,Schneider,schneider@example.org
Daniel,Wulf,daniel@example.org
Daniel,Wulf,daniel@example.org
Anke,Müller,anke@example.net

""".encode("utf-8"), content_type="text/csv")

    r = client.post('/control/event/dummy/dummy/orders/import/', {
        'file': file
    }, follow=True)
    doc = BeautifulSoup(r.content, "lxml")
    assert doc.select("select[name=orders]")
    assert doc.select("select[name=status]")
    assert doc.select("select[name=attendee_email]")
    assert b"Dieter" in r.content
    assert b"daniel@example.org" in r.content
    assert b"Anke" not in r.content
