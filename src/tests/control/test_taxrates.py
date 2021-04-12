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
from decimal import Decimal

from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Order, Organizer, Team, User
from pretix.base.models.orders import OrderFee


class TaxRateFormTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_change_items=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/settings/tax/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name_0'] = 'VAT'
        form_data['rate'] = '19.00'
        form_data['price_includes_tax'] = 'on'
        doc = self.post_doc('/control/event/%s/%s/settings/tax/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("VAT", doc.select("#page-wrapper table")[0].text)
        with scopes_disabled():
            assert self.event1.tax_rules.get(
                rate=19, price_includes_tax=True, eu_reverse_charge=False
            )

    def test_update(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['rate'] = '20.00'
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        assert doc.select(".alert-success")
        tr.refresh_from_db()
        assert tr.rate == Decimal('20.00')

    def test_delete(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("VAT", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert not self.event1.tax_rules.exists()

    def test_delete_item_existing(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
            self.event1.items.create(name="foo", default_price=12, tax_rule=tr)
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        self.assertIn("VAT", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.tax_rules.exists()

    def test_delete_default_rule(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
        self.event1.settings.tax_rate_default = tr
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        self.assertIn("VAT", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.tax_rules.exists()

    def test_delete_fee_existing(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
            o = self.event1.orders.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en',
            )
            o.fees.create(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.25'), tax_rate=Decimal('19.00'),
                          tax_value=Decimal('0.05'), tax_rule=tr)
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        self.assertIn("VAT", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.tax_rules.exists()

    def test_delete_orderpos_existing(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(rate=19, name="VAT")
            i = self.event1.items.create(name="foo", default_price=12)
            o = self.event1.orders.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=12, locale='en'
            )
            o.positions.create(
                item=i, price=12, tax_rule=tr, tax_rate=19, tax_value=12 - 12 / 1.19
            )
        doc = self.get_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/settings/tax/%s/delete' % (self.orga1.slug, self.event1.slug, tr.id),
                            form_data)
        self.assertIn("VAT", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.tax_rules.exists()
