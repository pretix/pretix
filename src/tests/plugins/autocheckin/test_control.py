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
import datetime

from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Item, Organizer, Team, User
from pretix.plugins.autocheckin.models import AutoCheckinRule


class AutoCheckinFormTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("dummy@dummy.dummy", "dummy")
        self.orga1 = Organizer.objects.create(name="CCC", slug="ccc")
        self.orga2 = Organizer.objects.create(name="MRM", slug="mrm")
        self.event1 = Event.objects.create(
            organizer=self.orga1,
            name="30C3",
            slug="30c3",
            plugins="pretix.plugins.autocheckin",
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.item1 = Item.objects.create(
            event=self.event1, name="Standard", default_price=0, position=1
        )
        t = Team.objects.create(
            organizer=self.orga1,
            can_change_event_settings=True,
            can_view_orders=True,
            can_change_items=True,
            all_events=True,
            can_create_events=True,
            can_change_orders=True,
            can_change_vouchers=True,
        )
        t.members.add(self.user)
        t = Team.objects.create(
            organizer=self.orga2,
            can_change_event_settings=True,
            can_view_orders=True,
            can_change_items=True,
            all_events=True,
            can_create_events=True,
            can_change_orders=True,
            can_change_vouchers=True,
        )
        t.members.add(self.user)
        self.client.login(email="dummy@dummy.dummy", password="dummy")

    def test_create(self):
        doc = self.get_doc(
            "/control/event/%s/%s/autocheckin/add" % (self.orga1.slug, self.event1.slug)
        )
        form_data = extract_form_fields(doc.select(".container-fluid form")[0])
        doc = self.post_doc(
            "/control/event/%s/%s/autocheckin/add"
            % (self.orga1.slug, self.event1.slug),
            form_data,
        )
        assert doc.select(".alert-success")
        assert self.event1.autocheckinrule_set.exists()

    def test_delete(self):
        acr = self.event1.autocheckinrule_set.create(
            mode=AutoCheckinRule.MODE_PAID,
            all_payment_methods=False,
            limit_payment_methods=["manual"],
        )
        doc = self.get_doc(
            "/control/event/%s/%s/autocheckin/%s/delete"
            % (self.orga1.slug, self.event1.slug, acr.id)
        )
        form_data = extract_form_fields(doc.select(".container-fluid form")[0])
        doc = self.post_doc(
            "/control/event/%s/%s/autocheckin/%s/delete"
            % (self.orga1.slug, self.event1.slug, acr.id),
            form_data,
        )
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.autocheckinrule_set.count() == 0

    def test_item_copy(self):
        with scopes_disabled():
            acr = self.event1.autocheckinrule_set.create(
                mode=AutoCheckinRule.MODE_PAID, all_products=False
            )
            acr.limit_products.add(self.item1)

        self.client.post(
            "/control/event/%s/%s/items/add" % (self.orga1.slug, self.event1.slug),
            {
                "name_0": "Intermediate",
                "default_price": "23.00",
                "tax_rate": "19.00",
                "copy_from": str(self.item1.pk),
                "has_variations": "1",
            },
        )
        with scopes_disabled():
            acr.refresh_from_db()
            i_new = Item.objects.get(name__icontains="Intermediate")
            assert i_new in acr.limit_products.all()

    def test_copy_event(self):
        with scopes_disabled():
            acr = self.event1.autocheckinrule_set.create(
                list=self.event1.checkin_lists.create(name="Test"),
                mode=AutoCheckinRule.MODE_PAID,
                all_products=False,
                all_sales_channels=False,
            )
            acr.limit_products.add(self.item1)
            acr.limit_sales_channels.add(
                self.orga1.sales_channels.get(identifier="web")
            )

        self.post_doc(
            "/control/events/add",
            {
                "event_wizard-current_step": "foundation",
                "event_wizard-prefix": "event_wizard",
                "foundation-organizer": self.orga2.pk,
                "foundation-locales": ("en",),
            },
        )
        self.post_doc(
            "/control/events/add",
            {
                "event_wizard-current_step": "basics",
                "event_wizard-prefix": "event_wizard",
                "basics-name_0": "33C3",
                "basics-slug": "33c3",
                "basics-date_from_0": "2016-12-27",
                "basics-date_from_1": "10:00:00",
                "basics-date_to_0": "2016-12-30",
                "basics-date_to_1": "19:00:00",
                "basics-location_0": "Hamburg",
                "basics-currency": "EUR",
                "basics-tax_rate": "19.00",
                "basics-locale": "en",
                "basics-timezone": "Europe/Berlin",
            },
        )
        self.post_doc(
            "/control/events/add",
            {
                "event_wizard-current_step": "copy",
                "event_wizard-prefix": "event_wizard",
                "copy-copy_from_event": self.event1.pk,
            },
        )

        with scopes_disabled():
            ev = Event.objects.get(slug="33c3")
            i_new = ev.items.first()
            acr_new = ev.autocheckinrule_set.get()

            assert i_new in acr_new.limit_products.all()
            assert list(acr_new.limit_sales_channels.all()) == [
                self.orga2.sales_channels.get(identifier="web")
            ]

            assert acr_new.list.event == ev
