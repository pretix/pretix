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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Maarten van den Berg, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
import decimal
import json
from decimal import Decimal

from django.core import mail as djmail
from django.test import TransactionTestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTestMixin, extract_form_fields

from pretix.base.models import (
    Event, Item, ItemVariation, Order, OrderPosition, Organizer, Quota,
    SeatingPlan, Team, User, Voucher, WaitingListEntry,
)


class VoucherFormTest(SoupTestMixin, TransactionTestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga, all_event_permissions=True)
        t.members.add(self.user)
        t.limit_events.add(self.event)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value='Red')
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value='Blue')
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=23)
        self.quota_tickets.items.add(self.ticket)

    def _create_voucher(self, data, expected_failure=False):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            if expected_failure:
                assert doc.select(".alert-danger, .has-error")
                assert count_before == self.event.vouchers.count()
            else:
                assert doc.select(".alert-success")
                assert count_before + 1 == self.event.vouchers.count()

    def _create_bulk_vouchers(self, data, expected_failure=False):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/bulk_add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/bulk_add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            if expected_failure:
                assert doc.select(".alert-danger")
                assert count_before == self.event.vouchers.count()
            else:
                assert doc.select(".alert-success")
                assert count_before + len(form_data.get('codes').split("\n")) == self.event.vouchers.count()

    def _change_voucher(self, v, data, expected_failure=False):
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, v.pk))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, v.pk), form_data)
        if expected_failure:
            assert doc.select(".alert-danger")
        else:
            assert doc.select(".alert-success")

    def test_list(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG')
        doc = self.client.get('/control/event/%s/%s/vouchers/' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()

    def test_csv(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG')
        doc = self.client.get('/control/event/%s/%s/vouchers/?download=yes' % (self.orga.slug, self.event.slug))
        assert doc.content.decode().strip() == '"Voucher code","Valid until","Product","Reserve quota",' \
                                               '"Bypass quota","Price effect","Value","Tag","Redeemed",' \
                                               '"Maximum usages","Seat","Comment"' \
                                               '\r\n"ABCDEFG","","Early-bird ticket","No","No","No effect","","","0",' \
                                               '"1","",""'

    def test_filter_status_valid(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=v' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()
        v.redeemed = 1
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=v' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()

    def test_filter_status_redeemed(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, redeemed=1)
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=r' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()
        v.redeemed = 0
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=r' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()

    def test_filter_status_expired(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() + datetime.timedelta(days=1))
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=e' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()
        v.valid_until = now() - datetime.timedelta(days=1)
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-status=e' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()

    def test_filter_tag(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG', comment='Foo', tag='bar')
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-tag=bar' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-tag=baz' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' not in doc.content.decode()

    def test_search_code(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG', comment='Foo')
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-search=ABCDEFG' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-search=Foo' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?filter-search=12345' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' not in doc.content.decode()

    def test_bulk_rng(self):
        rng = self.client.get('/control/event/%s/%s/vouchers/rng?num=7' % (self.orga.slug, self.event.slug))
        codes = json.loads(rng.content.decode('utf-8'))['codes']
        assert len(codes) == 7
        assert all([len(r) == 16 for r in codes])

    def test_display_voucher_code(self):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update({
            'itemvar': '%d' % self.ticket.pk
        })
        doc = self.post_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
            assert v.code in doc.select(".alert-success")[0].text
            assert count_before + 1 == self.event.vouchers.count()

    def test_create_voucher_for_addon_item(self):
        with scopes_disabled():
            c = self.event.categories.create(name="Foo", is_addon=True)
        self.ticket.category = c
        self.ticket.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk
        }, expected_failure=True)

    def test_create_non_blocking_item_voucher(self):
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item.pk == self.ticket.pk
        assert v.variation is None
        assert v.quota is None

    def test_create_non_blocking_variation_voucher(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk)
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item.pk == self.shirt.pk
        assert v.variation.pk == self.shirt_red.pk
        assert v.quota is None

    def test_create_non_blocking_quota_voucher(self):
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item is None
        assert v.variation is None
        assert v.quota.pk == self.quota_tickets.pk

    def test_create_blocking_item_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_blocking_item_voucher_quota_full(self):
        self._create_voucher({
            'itemvar': '%d' % self.shirt.pk,
            'block_quota': 'on'
        })

    def test_create_blocking_item_voucher_quota_full_invalid(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on',
            'valid_until_0': (now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() - datetime.timedelta(days=3)).strftime('%H:%M:%S')
        })

    def test_create_blocking_variation_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_short_code(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'code': 'ABC'
        }, expected_failure=True)

    def test_create_blocking_variation_voucher_quota_full(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_blocking_quota_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_blocking_quota_voucher_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_change_non_blocking_voucher(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_tickets.pk
        })
        v.refresh_from_db()
        assert v.item is None
        assert v.variation is None
        assert v.quota.pk == self.quota_tickets.pk

    def test_change_blocking_voucher_unchanged_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
        })
        v.refresh_from_db()
        assert v.block_quota

    def test_change_voucher_reduce_max_usages(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, max_usages=5, redeemed=3)
        self._change_voucher(v, {
            'max_usages': '2'
        }, expected_failure=True)

    def test_change_voucher_to_blocking_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'block_quota': 'on'
        }, expected_failure=True)

    def test_change_voucher_to_blocking_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'block_quota': 'on'
        })
        v.refresh_from_db()
        assert v.block_quota

    def test_change_voucher_validity_to_valid_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() - datetime.timedelta(days=3),
                                           block_quota=True)
        self._change_voucher(v, {
            'valid_until_0': (now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() + datetime.timedelta(days=3)).strftime('%H:%M:%S')
        }, expected_failure=True)
        v.refresh_from_db()
        assert v.valid_until < now()

    def test_change_voucher_validity_to_valid_quota_full_already_redeemed(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() - datetime.timedelta(days=3),
                                           block_quota=True, redeemed=1, max_usages=2)
        self._change_voucher(v, {
            'valid_until_0': (now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() + datetime.timedelta(days=3)).strftime('%H:%M:%S')
        })
        v.refresh_from_db()
        assert v.valid_until > now()

    def test_change_voucher_validity_to_valid_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() - datetime.timedelta(days=3),
                                           block_quota=True)
        self._change_voucher(v, {
            'valid_until_0': (now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() + datetime.timedelta(days=3)).strftime('%H:%M:%S')
        })
        v.refresh_from_db()
        assert v.valid_until > now()

    def test_change_item_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            ticket2 = Item.objects.create(event=self.event, name='Late-bird ticket', default_price=23)
            self.quota_tickets.items.add(ticket2)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % ticket2.pk,
        })

    def test_change_item_of_blocking_voucher_quota_full(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        with scopes_disabled():
            hoodie = Item.objects.create(event=self.event, name='Hoodie', default_price=23)
            self.quota_shirts.items.add(hoodie)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % hoodie.pk,
        }, expected_failure=True)

    def test_change_variation_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            self.quota_shirts.variations.remove(self.shirt_blue)
            self.quota_tickets.variations.add(self.shirt_blue)
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        })

    def test_change_variation_of_blocking_voucher_quota_full(self):
        with scopes_disabled():
            self.quota_shirts.variations.remove(self.shirt_blue)
            self.quota_tickets.variations.add(self.shirt_blue)
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        }, expected_failure=True)

    def test_change_quota_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_shirts.pk,
        })

    def test_change_quota_of_blocking_voucher_quota_full(self):
        with scopes_disabled():
            self.quota_shirts.size = 0
            self.quota_shirts.save()
            v = self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_shirts.pk,
        }, expected_failure=True)

    def test_change_item_of_blocking_voucher_without_quota_change(self):
        with scopes_disabled():
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            ticket2 = Item.objects.create(event=self.event, name='Standard Ticket', default_price=23)
            self.quota_tickets.items.add(ticket2)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % ticket2.pk,
        })

    def test_change_variation_of_blocking_voucher_without_quota_change(self):
        with scopes_disabled():
            self.quota_shirts.size = 0
            self.quota_shirts.save()
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        })

    def test_create_duplicate_code(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        self._create_voucher({
            'code': v.code,
        }, expected_failure=True)

    def test_change_code_to_duplicate(self):
        with scopes_disabled():
            v1 = self.event.vouchers.create(quota=self.quota_tickets)
            v2 = self.event.vouchers.create(quota=self.quota_tickets)
        self._change_voucher(v1, {
            'code': v2.code
        }, expected_failure=True)

    def test_create_bulk(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
        })

    def test_create_bulk_many(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH\nIJKLM\nNOPQR\nSTUVW\nXYZ',
            'itemvar': '%d' % self.ticket.pk,
        }, expected_failure=True)
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH\nIJKLM\nNOPQR\nSTUVW',
            'itemvar': '%d' % self.ticket.pk,
        })

    def test_create_blocking_bulk_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_blocking_bulk_quota_free(self):
        self.quota_tickets.size = 5
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        })

    def test_create_blocking_bulk_quota_partial(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_bulk_with_duplicate_code(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        self._create_bulk_vouchers({
            'codes': 'ABCDE\n%s' % v.code,
            'itemvar': '%d' % self.shirt.pk,
        }, expected_failure=True)

    def test_create_bulk_send(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foo@example.com\nbar@example.net'
        })
        assert len(djmail.outbox) == 2
        assert len([m for m in djmail.outbox if 'ABCDE' in m.body and m.to == ['foo@example.com']]) == 1
        assert len([m for m in djmail.outbox if 'DEFGH' in m.body and m.to == ['bar@example.net']]) == 1

    def test_create_bulk_send_csv(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number\nfoo@example.com,2'
        })
        assert len(djmail.outbox) == 1
        assert 'ABCDE' in djmail.outbox[0].body
        assert 'DEFGH' in djmail.outbox[0].body
        assert ['foo@example.com'] == djmail.outbox[0].to

    def test_create_bulk_send_csv_tag(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number,tag\nfoo@example.com,2,mytag'
        })
        assert len(djmail.outbox) == 1
        assert 'ABCDE' in djmail.outbox[0].body
        assert 'DEFGH' in djmail.outbox[0].body
        assert ['foo@example.com'] == djmail.outbox[0].to
        with scopes_disabled():
            assert Voucher.objects.get(code="ABCDE").tag == "mytag"

    def test_create_bulk_send_invalid_placeholder(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {order}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        }, expected_failure=True)

    def test_create_bulk_send_empty_subject(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': '',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        }, expected_failure=True)

    def test_create_bulk_send_invalid_mail_list(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo\nfoo@example.org'
        }, expected_failure=True)

    def test_create_bulk_send_invalid_mail_count(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo@example.org'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_header(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo@example.org,bar,baz'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_header_email(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'mail,number,tag\nfoooo@example.org,2,baz'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_unknown_header(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number,flop\nfoooo@example.org,2,baz'
        }, expected_failure=True)

    def test_delete_voucher(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert not doc.select(".alert-danger")

        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                            {}, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not self.event.vouchers.filter(pk=v.id).exists()

    def test_delete_voucher_redeemed(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets, redeemed=1)
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert doc.select(".alert-danger")

        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                            {}, follow=True)
        assert doc.select(".alert-danger")

    def test_subevent_optional(self):
        self.event.has_subevents = True
        self.event.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
        })

    def test_subevent_non_blocking_quota_no_date(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.save()

        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
        })

    def test_subevent_required_for_blocking(self):
        self.event.has_subevents = True
        self.event.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_subevent_blocking_quota_free(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.save()
            q2 = Quota.objects.create(event=self.event, name='Tickets', size=0, subevent=se2)
            q2.items.add(self.ticket)

        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on',
            'subevent': se1.pk
        })

    def test_subevent_blocking_quota_full(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            q2 = Quota.objects.create(event=self.event, name='Tickets', size=5, subevent=se2)
            q2.items.add(self.ticket)

        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on',
            'subevent': se1.pk
        }, expected_failure=True)

    def test_order_warning_deduplication(self):
        with scopes_disabled():
            shirt_voucher = Voucher.objects.create(
                event=self.event, item=self.shirt, price_mode='set', value=0.0, max_usages=100
            )

            shirt_order = Order.objects.create(
                code='DEDUP', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PAID,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                sales_channel=self.orga.sales_channels.get(identifier="web"),
                total=0, locale='en'
            )

            OrderPosition.objects.create(
                order=shirt_order,
                item=self.shirt,
                variation=self.shirt_red,
                price=decimal.Decimal("0"),
                voucher=shirt_voucher
            )

            OrderPosition.objects.create(
                order=shirt_order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=decimal.Decimal("0"),
                voucher=shirt_voucher
            )

        shirt_voucher.redeemed = 2
        shirt_voucher.save()

        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, shirt_voucher.pk))

        assert len(doc.select('.alert-warning ul li')) == 1  # Check that there's exactly 1 item in the warning list
        assert doc.text.count('Order DEDUP') == 1  # Check that the order is listed exactly once

    def test_tag_typeahead(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='AAAAAAA', tag='early-bird')
            self.event.vouchers.create(item=self.ticket, code='BBBBBBB', tag='early-vip')
            self.event.vouchers.create(item=self.ticket, code='CCCCCCC', tag='sponsor')

        url = '/control/event/%s/%s/vouchers/tags/typeahead' % (self.orga.slug, self.event.slug)
        resp = self.client.get(url + '?q=early')

        assert resp.status_code == 200
        data = json.loads(resp.content.decode())
        names = [r['name'] for r in data['results']]

        assert 'early-bird' in names
        assert 'early-vip' in names
        assert 'sponsor' not in names

    def test_tag_typeahead_excludes_waiting_list(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, code='AAAAAAA', tag='waiting-list')
            WaitingListEntry.objects.create(
                event=self.event, item=self.ticket, email='foo@example.com', voucher=v
            )
            self.event.vouchers.create(item=self.ticket, code='BBBBBBB', tag='walk-ins')

        url = '/control/event/%s/%s/vouchers/tags/typeahead' % (self.orga.slug, self.event.slug)
        resp = self.client.get(url + '?q=wa')

        assert resp.status_code == 200
        data = json.loads(resp.content.decode())
        names = [r['name'] for r in data['results']]

        assert 'walk-ins' in names
        assert 'waiting-list' not in names


class VoucherBulkEditFormTest(SoupTestMixin, TransactionTestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga, all_event_permissions=True)
        t.members.add(self.user)
        t.limit_events.add(self.event)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value='Red')
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value='Blue')
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)

        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=2)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=23)
        self.quota_tickets.items.add(self.ticket)
        self.url = f'/control/event/{self.orga.slug}/{self.event.slug}/vouchers/bulk_edit'

    def test_simple_edit(self):
        with scopes_disabled():
            self.event.vouchers.create(
                quota=self.quota_tickets,
                max_usages=10,
                price_mode="set",
                value=13,
            )
            self.event.vouchers.create(
                item=self.ticket,
                max_usages=10,
                price_mode="set",
                value=12,
            )

        doc = self.post_doc(self.url, {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        assert fields.get('bulkedit-max_usages') == '10'
        assert fields.get('bulkedit-price_mode') == 'set'
        assert not fields.get('bulkedit-value')
        fields.update({
            '_bulk': ['bulkedit__price', 'bulkeditmin_usages', 'bulkedittag', 'bulkeditshow_hidden_items'],
            'bulkedit-price_mode': 'percent',
            'bulkedit-value': '15',
            'bulkedit-min_usages': '3',
            'bulkedit-tag': 'tagged',
            'bulkedit-comment': 'This is a comment',  # will be ignored, as not included in _bulk
            'bulkedit-show_hidden_items': '',
        })
        doc = self.post_doc(self.url, fields, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.price_mode == "percent"
                assert v.value == Decimal("15.00")
                assert v.min_usages == 3
                assert v.tag == "tagged"
                assert v.comment == ""
                assert v.show_hidden_items is False

    def _update_all(self, data: dict, expect_error: str=None):
        doc = self.post_doc(self.url, {
            '__ALL': 'on',
        }, follow=True)
        fields = extract_form_fields(doc)
        fields.update(data)
        doc = self.post_doc(self.url, fields, follow=True)
        error_texts = [el.text for el in doc.select(".alert-danger, .has-error")]
        if expect_error:
            assert doc.select(".alert-danger")
            assert any(expect_error in t for t in error_texts), error_texts
        else:
            assert doc.select(".alert-success"), error_texts

    def test_change_itemvar_to_product(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets)
            self.event.vouchers.create(item=self.ticket)

        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.ticket.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.item == self.ticket
                assert not v.variation
                assert not v.quota

    def test_change_itemvar_to_variation(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets)
            self.event.vouchers.create(item=self.ticket)

        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.item == self.shirt
                assert v.variation == self.shirt_red
                assert not v.quota

    def test_change_itemvar_to_quota(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets)
            self.event.vouchers.create(item=self.ticket)

        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'q-{self.quota_tickets.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert not v.item
                assert not v.variation
                assert v.quota == self.quota_tickets

    def test_change_itemvar_to_all(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets)
            self.event.vouchers.create(item=self.ticket)

        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': '',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert not v.item
                assert not v.variation
                assert not v.quota

    def test_change_max_usages(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets, max_usages=15, redeemed=4)
            self.event.vouchers.create(item=self.ticket, max_usages=15, redeemed=2)

        self._update_all({
            '_bulk': ['bulkeditmax_usages'],
            'bulkedit-max_usages': '3',
        }, expect_error="already been redeemed 4 times")
        self._update_all({
            '_bulk': ['bulkeditmax_usages'],
            'bulkedit-max_usages': '4',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.max_usages == 4

    def _requires_one_more_quota(self, data: dict, quota=None):
        self._update_all(data, expect_error="no sufficient quota")
        quota = quota or self.quota_tickets
        quota.size += 1
        quota.save()
        self._update_all(data)

    def test_quota_check_change_item(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.shirt, block_quota=True, max_usages=2, redeemed=1)
            self.event.vouchers.create(item=self.shirt, block_quota=True, max_usages=3, redeemed=1)
        self._requires_one_more_quota({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.ticket.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.item == self.ticket

    def test_quota_check_change_variation(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=2, redeemed=1)
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=3, redeemed=1)
        self._requires_one_more_quota({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.shirt.pk}-{self.shirt_red.pk}',
        }, quota=self.quota_shirts)
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.item == self.shirt
                assert v.variation == self.shirt_red

    def test_quota_check_change_item_with_variations(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=2, redeemed=1)
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=3, redeemed=1)
        self._requires_one_more_quota({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.shirt.pk}',
        }, quota=self.quota_shirts)
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.item == self.shirt
                assert not v.variation

    def test_quota_check_change_expired_to_valid(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=2)
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=1, valid_until=now() - datetime.timedelta(days=1))
        self._requires_one_more_quota({
            '_bulk': ['bulkeditvalid_until'],
            'bulkedit-valid_until_0': '',
            'bulkedit-valid_until_1': '',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert not v.valid_until

    def test_quota_check_change_max_usages(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=2)
            self.event.vouchers.create(item=self.ticket, block_quota=True, max_usages=1, redeemed=1)
        self._requires_one_more_quota({
            '_bulk': ['bulkeditmax_usages'],
            'bulkedit-max_usages': '2',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.max_usages == 2

    def test_quota_check_no_change(self):
        with scopes_disabled():
            # Technically overbooked, but we don't have a diff in quota
            self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
            self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
            self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'{self.shirt.pk}-{self.shirt_blue.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.variation == self.shirt_blue

    def test_quota_check_change_subevent(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())
            self.quota_tickets.subevent = se1
            self.quota_tickets.save()
            Quota.objects.create(event=self.event, subevent=se2, name='Tickets', size=3)
            self.event.vouchers.create(item=self.ticket, block_quota=True, subevent=se2)
            self.event.vouchers.create(item=self.ticket, block_quota=True, subevent=se2)
            self.event.vouchers.create(item=self.ticket, block_quota=True, subevent=se2)
        self._requires_one_more_quota({
            '_bulk': ['bulkeditsubevent'],
            'bulkedit-subevent': f'{se1.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.subevent == se1

    def test_change_subevent_quota_invalid(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())
            self.quota_tickets.subevent = se1
            self.quota_tickets.save()
            v1 = self.event.vouchers.create(quota=self.quota_tickets, block_quota=True, subevent=se1)
        self._update_all({
            '_bulk': ['bulkeditsubevent'],
            'bulkedit-subevent': f'{se2.pk}',
        }, expect_error="selected quota does not match the selected subevent")
        self._update_all({
            '_bulk': ['bulkeditsubevent'],
            'bulkedit-subevent': '',
        }, expect_error="has no date selected")
        v1.quota = None
        v1.item = self.ticket
        v1.save()
        self._update_all({
            '_bulk': ['bulkeditsubevent'],
            'bulkedit-subevent': '',
        }, expect_error="If you want this voucher to block quota, you need to select a specific date")
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.subevent == se1

    def test_change_missing_itemvar_with_block_quota(self):
        with scopes_disabled():
            self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
            self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': '',
        }, expect_error="You need to select a specific product or quota if this voucher should reserve")
        self._update_all({
            '_bulk': ['bulkedititemvar', 'bulkeditblock_quota'],
            'bulkedit-itemvar': '',
            'bulkedit-block_quota': '',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert not v.subevent
                assert not v.block_quota

    def test_change_subevent_and_quota(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())
            self.quota_tickets.subevent = se1
            self.quota_tickets.save()
            q2 = Quota.objects.create(event=self.event, subevent=se2, name='Tickets', size=3)
            self.event.vouchers.create(quota=self.quota_tickets, block_quota=True, subevent=se1)
        self._update_all({
            '_bulk': ['bulkedititemvar', 'bulkeditsubevent'],
            'bulkedit-subevent': f'{se2.pk}',
            'bulkedit-itemvar': f'q-{q2.pk}',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.subevent == se2
                assert v.quota == q2

    def test_quota_check_change_block_quota(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, max_usages=3)
        self._requires_one_more_quota({
            '_bulk': ['bulkeditblock_quota'],
            'bulkedit-block_quota': 'on',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.block_quota

    def test_ignore_quota(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, max_usages=3)
        self._update_all({
            '_bulk': ['bulkeditblock_quota', 'bulkeditallow_ignore_quota'],
            'bulkedit-block_quota': 'on',
            'bulkedit-allow_ignore_quota': 'on',
        })
        with scopes_disabled():
            for v in self.event.vouchers.all():
                assert v.block_quota
                assert v.allow_ignore_quota

    @scopes_disabled()
    def _create_seat(self, **kwargs):
        plan = SeatingPlan.objects.create(
            name="Plan", organizer=self.orga, layout="{}"
        )
        self.event.seating_plan = plan
        self.event.save()
        return self.event.seats.create(seat_number="A1", product=self.ticket, seat_guid="A1", **kwargs)

    def test_seated_unsupported(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, max_usages=1, seat=self._create_seat())
        self._update_all({
            '_bulk': ['bulkeditmax_usages'],
            'bulkedit-max_usages': '2',
        }, expect_error="Changing the maximum number of usages in bulk is not supported")
        self._update_all({
            '_bulk': ['bulkeditsubevent'],
            'bulkedit-subevent': '',
        }, expect_error="Changing the date in bulk is not supported")
        self._update_all({
            '_bulk': ['bulkedititemvar'],
            'bulkedit-itemvar': f'q-{self.quota_tickets.pk}',
        }, expect_error="Changing the product to a quota is not supported")

    def test_seat_changed_to_valid_needs_to_be_available(self):
        with scopes_disabled():
            seat = self._create_seat(blocked=True)
            self.event.vouchers.create(item=self.ticket, max_usages=1, valid_until=now() - datetime.timedelta(days=1), seat=seat)

        self._update_all({
            '_bulk': ['bulkeditvalid_until'],
            'bulkedit-valid_until_0': '',
            'bulkedit-valid_until_1': '',
        }, expect_error="not all assigned seats of the vouchers are still available")

        seat.blocked = False
        seat.save()
        self._update_all({
            '_bulk': ['bulkeditvalid_until'],
            'bulkedit-valid_until_0': '',
            'bulkedit-valid_until_1': '',
        })

    def test_seat_changed_to_valid_needs_to_be_available_subevents(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            seat = self._create_seat(subevent=se1, blocked=True)
            self.event.vouchers.create(item=self.ticket, max_usages=1, valid_until=now() - datetime.timedelta(days=1), seat=seat, subevent=se1)

        self._update_all({
            '_bulk': ['bulkeditvalid_until'],
            'bulkedit-valid_until_0': '',
            'bulkedit-valid_until_1': '',
        }, expect_error="not all assigned seats of the vouchers are still available")

        seat.blocked = False
        seat.save()
        self._update_all({
            '_bulk': ['bulkeditvalid_until'],
            'bulkedit-valid_until_0': '',
            'bulkedit-valid_until_1': '',
        })
