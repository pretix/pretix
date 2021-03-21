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

from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Item, Organizer, Team, User
from pretix.plugins.ticketoutputpdf.models import TicketLayoutItem


class TicketLayoutFormTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            plugins='pretix.plugins.ticketoutputpdf',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0, position=1)
        t = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_view_orders=True,
                                can_change_items=True, all_events=True, can_create_events=True,
                                can_change_vouchers=True, can_change_orders=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/pdfoutput/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name'] = 'Layout 1'
        doc = self.post_doc('/control/event/%s/%s/pdfoutput/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("Layout 1", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.ticket_layouts.get(
                default=True, name='Layout 1'
            )

    def test_set_default(self):
        with scopes_disabled():
            bl1 = self.event1.ticket_layouts.create(name="Layout 1", default=True)
            bl2 = self.event1.ticket_layouts.create(name="Layout 2")
        self.post_doc('/control/event/%s/%s/pdfoutput/%s/default' % (self.orga1.slug, self.event1.slug, bl2.id), {})
        bl1.refresh_from_db()
        assert not bl1.default
        bl2.refresh_from_db()
        assert bl2.default

    def test_delete(self):
        with scopes_disabled():
            bl1 = self.event1.ticket_layouts.create(name="Layout 1", default=True)
            bl2 = self.event1.ticket_layouts.create(name="Layout 2")
        doc = self.get_doc('/control/event/%s/%s/pdfoutput/%s/delete' % (self.orga1.slug, self.event1.slug, bl1.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/pdfoutput/%s/delete' % (self.orga1.slug, self.event1.slug, bl1.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("Layout 1", doc.select("#page-wrapper")[0].text)
        with scopes_disabled():
            assert self.event1.ticket_layouts.count() == 1
        bl2.refresh_from_db()
        assert bl2.default

    def test_set_on_item(self):
        with scopes_disabled():
            self.event1.ticket_layouts.create(name="Layout 1", default=True)
            bl2 = self.event1.ticket_layouts.create(name="Layout 2")
        doc = self.get_doc('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id))
        d = extract_form_fields(doc.select('.container-fluid form')[0])
        d.update({
            'name_0': 'Standard',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes',
            'ticketlayoutitem_web-layout': bl2.pk,
            'sales_channels': 'web',
        })
        self.client.post('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id), d)
        with scopes_disabled():
            assert TicketLayoutItem.objects.get(item=self.item1, layout=bl2)
        doc = self.get_doc('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id))
        d = extract_form_fields(doc.select('.container-fluid form')[0])
        d.update({
            'name_0': 'Standard',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes',
            'sales_channels': 'web',
            'ticketlayoutitem_web-layout': '',
        })
        self.client.post('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id), d)
        with scopes_disabled():
            assert not TicketLayoutItem.objects.filter(item=self.item1, layout=bl2).exists()

    def test_item_copy(self):
        with scopes_disabled():
            bl2 = self.event1.ticket_layouts.create(name="Layout 2")
            TicketLayoutItem.objects.create(item=self.item1, layout=bl2)
        self.client.post('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), {
            'name_0': 'Intermediate',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'copy_from': str(self.item1.pk),
            'has_variations': '1'
        })
        with scopes_disabled():
            i_new = Item.objects.get(name__icontains='Intermediate')
            assert TicketLayoutItem.objects.get(item=i_new, layout=bl2)
            assert TicketLayoutItem.objects.get(item=self.item1, layout=bl2)

    def test_copy_event(self):
        with scopes_disabled():
            bl2 = self.event1.ticket_layouts.create(name="Layout 2")
            TicketLayoutItem.objects.create(item=self.item1, layout=bl2)
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en',)
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '19.00',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': self.event1.pk
        })

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            i_new = ev.items.first()
            bl_new = ev.ticket_layouts.first()
            assert TicketLayoutItem.objects.get(item=i_new, layout=bl_new)
