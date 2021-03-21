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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Maico Timmerman
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
import json
import time
from io import BytesIO
from zipfile import ZipFile

from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTest

from pretix.base.models import Event, Order, Organizer, Team, User


class EventShredderTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True, can_change_orders=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.order = Order.objects.create(
            code='FOO', event=self.event1, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now(),
            total=14, locale='en'
        )

        self.client.login(email='dummy@dummy.dummy', password='dummy')
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time()) * 2
        session.save()

    def test_shred_simple(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'slug': self.event1.slug
        })
        assert doc.select('.alert-success')
        self.order.refresh_from_db()
        assert not self.order.email

    def test_shred_password_wrong(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'test'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email

    def test_shred_confirm_code_wrong(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'][::-1] + 'A',
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'dummy'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email

    def test_shred_constraints(self):
        self.event1.live = True
        self.event1.save()
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert not doc.select("input[value=order_emails]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select('.alert-danger')

    def test_shred_something_happened(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        self.order.log_action('dummy')
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'dummy'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email
