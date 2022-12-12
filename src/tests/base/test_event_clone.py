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
# This file contains Apache-licensed contributions copyrighted by: Christopher Dambamuromo, Enrique Saez, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import datetime
from datetime import timedelta

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer, Question, SeatingPlan
from pretix.base.models.items import ItemAddOn, ItemBundle, ItemMetaValue


@pytest.mark.django_db
@scopes_disabled()
def test_full_clone_same_organizer():
    organizer = Organizer.objects.create(name='Dummy', slug='dummy')
    membership_type = organizer.membership_types.create(name="Membership")
    plan = SeatingPlan.objects.create(name="Plan", organizer=organizer, layout="{}")

    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now(),
        date_admission=now() - timedelta(hours=1),
        date_to=now() + timedelta(hours=1),
        testmode=True,
        seating_plan=plan,
    )

    item_meta = event.item_meta_properties.create(name="Bla")
    tax_rule = event.tax_rules.create(name="VAT", rate=19)
    category = event.categories.create(name="Tickets")

    q1 = event.quotas.create(name="Quota 1", size=5)
    q2 = event.quotas.create(name="Quota 2", size=0, closed=True)

    item1 = event.items.create(category=category, tax_rule=tax_rule, name="Ticket", default_price=23,
                               grant_membership_type=membership_type, hidden_if_available=q2)
    # todo: test that item pictures are copied, not linked
    ItemMetaValue.objects.create(item=item1, property=item_meta, value="Foo")
    assert item1.meta_data
    item2 = event.items.create(category=category, tax_rule=tax_rule, name="T-shirt", default_price=15)
    item2v = item2.variations.create(value="red", default_price=15)
    item2v.meta_values.create(property=item_meta, value="Bar")
    item2.require_membership_types.add(membership_type)
    ItemAddOn.objects.create(base_item=item1, addon_category=category)
    ItemBundle.objects.create(base_item=item1, bundled_item=item2, bundled_variation=item2v)

    q1.items.add(item1)
    q2.items.add(item2)
    q2.variations.add(item2v)

    event.discounts.create(internal_name="Fake discount")
    question1 = event.questions.create(question="Yes or no", type=Question.TYPE_BOOLEAN)
    question2 = event.questions.create(question="Size", type=Question.TYPE_CHOICE_MULTIPLE,
                                       dependency_question=question1)
    question2.options.create(answer="Foobar")

    event.seat_category_mappings.create(
        layout_category='Stalls', product=item1
    )
    event.seats.create(seat_number="A1", product=item1, seat_guid="A1")

    clist = event.checkin_lists.create(name="Default", rules={
        "or": [
            {
                "inList": [
                    {"var": "product"}, {
                        "objectList": [
                            {"lookup": ["product", str(item1.pk), "Ticket"]},
                        ]
                    }
                ]
            },
            {
                "inList": [
                    {"var": "variation"}, {
                        "objectList": [
                            {"lookup": ["variation", str(item2v.pk), "T-shirt - red"]},
                        ]
                    }
                ]
            }
        ],
    })
    clist.limit_products.add(item1)

    copied_event = Event.objects.create(
        organizer=organizer, name='Dummy2', slug='dummy2',
        date_from=datetime.datetime(2022, 4, 15, 9, 0, 0, tzinfo=datetime.timezone.utc),
    )
    copied_event.copy_data_from(event)
    copied_event.refresh_from_db()
    event.refresh_from_db()

    # Verify event properties
    assert abs(copied_event.date_admission - (copied_event.date_from - timedelta(hours=1))) < timedelta(minutes=1)
    assert copied_event.testmode

    # Verify that we actually *copied*, not just moved objects over
    assert event.tax_rules.count() == copied_event.tax_rules.count() == 1
    assert event.checkin_lists.count() == copied_event.checkin_lists.count() == 1
    assert event.quotas.count() == copied_event.quotas.count() == 2
    assert event.items.count() == copied_event.items.count() == 2
    assert event.discounts.count() == copied_event.discounts.count() == 1
    assert event.questions.count() == copied_event.questions.count() == 2
    assert event.seat_category_mappings.count() == copied_event.seat_category_mappings.count() == 1
    assert event.seats.count() == copied_event.seats.count() == 1

    # Verify relationship integrity
    copied_q1 = copied_event.quotas.get(name=q1.name)
    copied_q2 = copied_event.quotas.get(name=q2.name)

    copied_item1 = copied_event.items.get(name=item1.name)
    copied_item2 = copied_event.items.get(name=item2.name)
    assert copied_item1.tax_rule == copied_event.tax_rules.get()
    assert copied_item1.category == copied_event.categories.get()
    assert copied_item1.meta_data == item1.meta_data
    assert copied_item2.variations.get().meta_data == item2v.meta_data
    assert copied_item1.hidden_if_available == copied_q2
    assert copied_item1.grant_membership_type == membership_type
    assert copied_item2.variations.count() == 1
    assert copied_item2.require_membership_types.get() == membership_type
    assert copied_item1.addons.get().addon_category == copied_event.categories.get()
    assert copied_item1.bundles.get().bundled_item == copied_item2
    assert copied_item1.bundles.get().bundled_variation == copied_item2.variations.get()
    assert copied_q1.items.get() == copied_item1
    assert copied_q2.items.get() == copied_item2
    assert copied_q2.variations.get() == copied_item2.variations.get()

    copied_question1 = copied_event.questions.get(type=question1.type)
    copied_question2 = copied_event.questions.get(type=question2.type)
    assert copied_question2.dependency_question == copied_question1
    assert copied_question2.dependency_question == copied_question1

    assert copied_event.seat_category_mappings.get().product == copied_item1
    assert copied_event.seats.get().product == copied_item1

    copied_clist = copied_event.checkin_lists.get()
    assert copied_clist.rules == {
        "or": [
            {
                "inList": [
                    {"var": "product"}, {
                        "objectList": [
                            {"lookup": ["product", str(copied_item1.pk), "Ticket"]},
                        ]
                    }
                ]
            },
            {
                "inList": [
                    {"var": "variation"}, {
                        "objectList": [
                            {"lookup": ["variation", str(copied_item2.variations.get().pk), "T-shirt - red"]},
                        ]
                    }
                ]
            }
        ],
    }
    assert copied_clist.limit_products.get() == copied_item1

    # todo: test that the plugin hook is called
    # todo: test custom style
    # todo: test that files in settings are copied not linked
    # todo: test that references to questions in ticket layouts are updated


@pytest.mark.django_db
@scopes_disabled()
def test_full_clone_cross_organizer_differences():
    organizer = Organizer.objects.create(name='Dummy', slug='dummy')
    organizer2 = Organizer.objects.create(name='Dummy2', slug='dummy2')
    membership_type = organizer.membership_types.create(name="Membership")
    plan = SeatingPlan.objects.create(name="Plan", organizer=organizer, layout="{}")

    event = Event.objects.create(
        organizer=organizer, name='Dummy', slug='dummy',
        date_from=now(),
        date_admission=now() - timedelta(hours=1),
        date_to=now() + timedelta(hours=1),
        testmode=True,
        seating_plan=plan,
    )

    item1 = event.items.create(name="Ticket", default_price=23,
                               grant_membership_type=membership_type)
    item2 = event.items.create(name="T-shirt", default_price=15)
    item2.require_membership_types.add(membership_type)

    copied_event = Event.objects.create(
        organizer=organizer2, name='Dummy2', slug='dummy2',
        date_from=datetime.datetime(2022, 4, 15, 9, 0, 0, tzinfo=datetime.timezone.utc),
    )
    copied_event.copy_data_from(event)
    copied_event.refresh_from_db()
    event.refresh_from_db()

    assert organizer2.seating_plans.count() == 1
    assert organizer2.seating_plans.get().layout == plan.layout
    assert copied_event.seating_plan.organizer == organizer2
    assert event.seating_plan.organizer == organizer

    copied_item1 = copied_event.items.get(name=item1.name)
    copied_item2 = copied_event.items.get(name=item2.name)
    assert copied_item1.grant_membership_type is None
    assert copied_item2.require_membership_types.count() == 0
