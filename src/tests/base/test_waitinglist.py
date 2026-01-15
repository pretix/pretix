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
from datetime import timedelta

from django.core import mail as djmail
from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    Event, Item, ItemVariation, Organizer, Quota, Voucher, WaitingListEntry,
)
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.waitinglist import (
    assign_automatically, process_waitinglist,
)
from pretix.testutils.scope import classscope


class WaitingListTestCase(TestCase):

    def setUp(self):
        self.o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=self.o, name='Dummy', slug='dummy',
            date_from=now(), live=True
        )
        djmail.outbox = []
        with scope(organizer=self.o):
            self.quota = Quota.objects.create(name="Test", size=2, event=self.event)
            self.item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                             admission=True)
            self.item2 = Item.objects.create(event=self.event, name="T-Shirt", default_price=23)
            self.item3 = Item.objects.create(event=self.event, name="Goodie", default_price=23)
            self.var1 = ItemVariation.objects.create(item=self.item2, value='S')
            self.var2 = ItemVariation.objects.create(item=self.item2, value='M')
            self.var3 = ItemVariation.objects.create(item=self.item3, value='Fancy')

    @classscope(attr='o')
    def test_send_unavailable(self):
        self.quota.items.add(self.item1)
        self.quota.size = 0
        self.quota.save()
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='foo@bar.com'
        )
        with self.assertRaises(WaitingListException):
            wle.send_voucher()

    @classscope(attr='o')
    def test_send_no_seat(self):
        self.quota.items.add(self.item1)
        self.quota.size = 10
        self.quota.save()
        self.event.seat_category_mappings.create(
            layout_category='Stalls', product=self.item1
        )
        self.event.seats.create(seat_number="Foo", product=self.item1, seat_guid="Foo", blocked=True)
        self.event.seats.create(seat_number="Bar", product=self.item1, seat_guid="Bar", blocked=True)
        self.event.seats.create(seat_number="Baz", product=self.item1, seat_guid="Baz", blocked=True)
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='foo@bar.com'
        )
        with self.assertRaises(WaitingListException):
            wle.send_voucher()
        self.event.seats.create(seat_number="Baz", product=self.item1, seat_guid="Baz", blocked=False)
        wle.send_voucher()

    @classscope(attr='o')
    def test_send_double(self):
        self.quota.variations.add(self.var1)
        self.quota.size = 1
        self.quota.save()
        v = Voucher.objects.create(quota=self.quota, event=self.event, block_quota=True, redeemed=1)
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='foo@bar.com', voucher=v
        )
        with self.assertRaises(WaitingListException):
            wle.send_voucher()

    @classscope(attr='o')
    def test_send_variation(self):
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='foo@bar.com'
        )
        wle.send_voucher()
        wle.refresh_from_db()

        assert wle.voucher
        assert wle.voucher.item == wle.item
        assert wle.voucher.variation == wle.variation
        assert wle.email in wle.voucher.comment
        assert wle.voucher.block_quota
        assert wle.voucher.max_usages == 1
        assert wle.voucher.event == self.event

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [wle.email]

    @classscope(attr='o')
    def test_send_custom_validity(self):
        self.event.settings.set('waiting_list_hours', 24)
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='foo@bar.com',
            name_parts={'_legacy': 'Max'}
        )
        wle.send_voucher()
        wle.refresh_from_db()

        assert 3600 * 23 < (wle.voucher.valid_until - now()).seconds < 3600 * 24

        assert 'foo@bar.com' in wle.voucher.comment
        assert 'Max' in wle.voucher.comment

    def test_send_auto(self):
        with scope(organizer=self.o):
            self.quota.variations.add(self.var1)
            self.quota.size = 7
            self.quota.save()
            for i in range(10):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item1, email='bar{}@bar.com'.format(i)
                )

        assign_automatically.apply(args=(self.event.pk,))
        with scope(organizer=self.o):
            assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 3
            assert Voucher.objects.count() == 17
            assert sorted(list(WaitingListEntry.objects.filter(voucher__isnull=True).values_list('email', flat=True))) == [
                'foo7@bar.com', 'foo8@bar.com', 'foo9@bar.com'
            ]

    def test_send_auto_respect_priority(self):
        with scope(organizer=self.o):
            self.quota.variations.add(self.var1)
            self.quota.size = 7
            self.quota.save()
            for i in range(10):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i),
                    priority=i
                )
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item1, email='bar{}@bar.com'.format(i),
                    priority=i
                )

        assign_automatically.apply(args=(self.event.pk,))
        with scope(organizer=self.o):
            assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 3
            assert Voucher.objects.count() == 17
            assert sorted(list(WaitingListEntry.objects.filter(voucher__isnull=True).values_list('email', flat=True))) == [
                'foo0@bar.com', 'foo1@bar.com', 'foo2@bar.com'
            ]

    def test_send_auto_quota_infinite(self):
        with scope(organizer=self.o):
            self.quota.variations.add(self.var1)
            self.quota.size = None
            self.quota.save()
            for i in range(10):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item1, email='bar{}@bar.com'.format(i)
                )

        assign_automatically.apply(args=(self.event.pk,))
        with scope(organizer=self.o):
            assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 10
            assert Voucher.objects.count() == 10

    def test_send_periodic_event_over(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', True)
        self.event.presale_end = now() - timedelta(days=1)
        self.event.save()
        with scope(organizer=self.o):
            for i in range(5):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
        process_waitinglist(None)
        with scope(organizer=self.o):
            assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 5
            assert Voucher.objects.count() == 0
            self.event.presale_end = now() + timedelta(days=1)
            self.event.save()

    def test_send_periodic(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', True)
        with scope(organizer=self.o):
            for i in range(5):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
        process_waitinglist(None)
        with scope(organizer=self.o):
            assert Voucher.objects.count() == 5

    def test_send_periodic_disabled(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', False)
        with scope(organizer=self.o):
            for i in range(5):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
        process_waitinglist(None)
        with scope(organizer=self.o):
            assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 5
            assert Voucher.objects.count() == 0

    def test_send_periodic_disabled2(self):
        self.event.settings.set('waiting_list_enabled', False)
        self.event.settings.set('waiting_list_auto', True)
        with scope(organizer=self.o):
            for i in range(5):
                WaitingListEntry.objects.create(
                    event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
                )
        process_waitinglist(None)
        with scope(organizer=self.o):
            assert Voucher.objects.count() == 5

    @classscope(attr='o')
    def test_get_rank_basic(self):
        """Test rank calculation for basic waiting list entries (no voucher)"""
        # Create 5 entries
        entries = []
        for i in range(5):
            entry = WaitingListEntry.objects.create(
                event=self.event, item=self.item1, email='user{}@bar.com'.format(i)
            )
            entries.append(entry)
        
        # First entry should have rank 1
        assert entries[0].get_rank() == 1
        # Second entry should have rank 2
        assert entries[1].get_rank() == 2
        # Last entry should have rank 5
        assert entries[4].get_rank() == 5

    @classscope(attr='o')
    def test_get_rank_returns_zero_for_valid_voucher(self):
        """Test that entries with valid, unredeemed vouchers return 0"""
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user@bar.com'
        )
        wle.save()
        assert wle.get_rank() != 0

        v = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=0,
            valid_until=now() + timedelta(days=1)
        )
        wle.voucher = v
        wle.save()
        
        assert wle.get_rank() == 0

    @classscope(attr='o')
    def test_get_rank_returns_none_for_redeemed_voucher(self):
        """Test that fully redeemed vouchers return None"""
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user@bar.com'
        )
        wle.save()
        assert wle.get_rank() == 1

        v = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=1
        )
        wle.voucher = v
        wle.save()
        
        assert wle.get_rank() is None

    @classscope(attr='o')
    def test_get_rank_returns_none_for_expired_voucher(self):
        """Test that expired vouchers return None"""
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user@bar.com'
        )
        v = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=0,
            valid_until=now() - timedelta(days=1)
        )
        wle.voucher = v
        wle.save()
        
        assert wle.get_rank() is None

    @classscope(attr='o')
    def test_get_rank_includes_unredeemed_voucher_holders_in_count(self):
        """Test that entries with valid vouchers are included when counting ranks for entries without vouchers"""
        # Create entry with valid voucher
        wle1 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user1@bar.com'
        )
        v = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=0,
            valid_until=now() + timedelta(days=1)
        )
        wle1.voucher = v
        wle1.save()
        
        # Create entry without voucher
        wle2 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user2@bar.com'
        )
        
        # Entry with voucher should return 0
        assert wle1.get_rank() == 0
        # Entry without voucher should have rank 2 (1 for voucher holder + 1 for itself)
        assert wle2.get_rank() == 2

    @classscope(attr='o')
    def test_get_rank_excludes_redeemed_expired_from_count(self):
        """Test that redeemed and expired vouchers are excluded when counting ranks"""
        # Create entry with expired voucher
        wle1 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user1@bar.com'
        )
        v_expired = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=0,
            valid_until=now() - timedelta(days=1)
        )
        wle1.voucher = v_expired
        wle1.save()
        
        # Create entry with redeemed voucher
        wle2 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user2@bar.com'
        )
        v_redeemed = Voucher.objects.create(
            event=self.event, item=self.item1, max_usages=1, redeemed=1
        )
        wle2.voucher = v_redeemed
        wle2.save()
        
        # Create entry without voucher
        wle3 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user3@bar.com'
        )
        
        # Expired and redeemed should return None
        assert wle1.get_rank() is None
        assert wle2.get_rank() is None
        # Entry without voucher should have rank 1 (expired/redeemed are excluded)
        assert wle3.get_rank() == 1

    @classscope(attr='o')
    def test_get_rank_ordering(self):
        """Verify rank respects priority and created date ordering"""
        # Create entries with different priorities and timestamps
        wle1 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user1@bar.com',
            priority=10
        )
        wle2 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user2@bar.com',
            priority=5
        )
        wle3 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user3@bar.com',
            priority=10  # Same priority as wle1, but created later
        )
        
        # Higher priority should have lower rank (rank 1)
        assert wle1.get_rank() == 1
        # Lower priority should have higher rank (rank 3)
        assert wle2.get_rank() == 3
        # Same priority, created earlier should have lower rank (rank 2)
        assert wle3.get_rank() == 2

    @classscope(attr='o')
    def test_get_rank_subevent(self):
        """Test rank calculation with subevents"""
        from pretix.base.models import SubEvent
        
        subevent1 = SubEvent.objects.create(event=self.event, name='Day 1', date_from=now())
        subevent2 = SubEvent.objects.create(event=self.event, name='Day 2', date_from=now())
        
        # Create entries for different subevents
        wle1 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user1@bar.com',
            subevent=subevent1
        )
        wle2 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user2@bar.com',
            subevent=subevent1
        )
        wle3 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user3@bar.com',
            subevent=subevent2
        )
        
        # Ranks should be separate per subevent
        assert wle1.get_rank() == 1
        assert wle2.get_rank() == 2
        # Entry for different subevent should have rank 1 (separate list)
        assert wle3.get_rank() == 1

    @classscope(attr='o')
    def test_get_rank_item_variation(self):
        """Test rank is per item/variation combination"""
        # Create entries for different items
        wle1 = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='user1@bar.com'
        )
        wle2 = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='user2@bar.com'
        )
        wle3 = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='user3@bar.com'
        )
        
        # Ranks should be separate per item/variation
        assert wle1.get_rank() == 1
        assert wle2.get_rank() == 1
        assert wle3.get_rank() == 2
