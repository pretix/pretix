from datetime import timedelta

from django.core import mail as djmail
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    Event, Item, ItemVariation, Organizer, Quota, Voucher, WaitingListEntry,
)
from pretix.base.models.waitinglist import WaitingListException
from pretix.base.services.waitinglist import (
    assign_automatically, process_waitinglist,
)


class WaitingListTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), live=True
        )

    def setUp(self):
        djmail.outbox = []
        self.quota = Quota.objects.create(name="Test", size=2, event=self.event)
        self.item1 = Item.objects.create(event=self.event, name="Ticket", default_price=23,
                                         admission=True)
        self.item2 = Item.objects.create(event=self.event, name="T-Shirt", default_price=23)
        self.item3 = Item.objects.create(event=self.event, name="Goodie", default_price=23)
        self.var1 = ItemVariation.objects.create(item=self.item2, value='S')
        self.var2 = ItemVariation.objects.create(item=self.item2, value='M')
        self.var3 = ItemVariation.objects.create(item=self.item3, value='Fancy')

    def test_send_unavailable(self):
        self.quota.items.add(self.item1)
        self.quota.size = 0
        self.quota.save()
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item1, email='foo@bar.com'
        )
        with self.assertRaises(WaitingListException):
            wle.send_voucher()

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

    def test_send_custom_validity(self):
        self.event.settings.set('waiting_list_hours', 24)
        wle = WaitingListEntry.objects.create(
            event=self.event, item=self.item2, variation=self.var1, email='foo@bar.com'
        )
        wle.send_voucher()
        wle.refresh_from_db()

        assert 3600 * 23 < (wle.voucher.valid_until - now()).seconds < 3600 * 24

    def test_send_auto(self):
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
        assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 3
        assert Voucher.objects.count() == 17
        assert sorted(list(WaitingListEntry.objects.filter(voucher__isnull=True).values_list('email', flat=True))) == [
            'foo7@bar.com', 'foo8@bar.com', 'foo9@bar.com'
        ]

    def test_send_auto_respect_priority(self):
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
        assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 3
        assert Voucher.objects.count() == 17
        assert sorted(list(WaitingListEntry.objects.filter(voucher__isnull=True).values_list('email', flat=True))) == [
            'foo0@bar.com', 'foo1@bar.com', 'foo2@bar.com'
        ]

    def test_send_auto_quota_infinite(self):
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
        assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 10
        assert Voucher.objects.count() == 10

    def test_send_periodic_event_over(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', True)
        self.event.presale_end = now() - timedelta(days=1)
        self.event.save()
        for i in range(5):
            WaitingListEntry.objects.create(
                event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
            )
        process_waitinglist(None)
        assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 5
        assert Voucher.objects.count() == 0
        self.event.presale_end = now() + timedelta(days=1)
        self.event.save()

    def test_send_periodic(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', True)
        for i in range(5):
            WaitingListEntry.objects.create(
                event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
            )
        process_waitinglist(None)
        assert Voucher.objects.count() == 5

    def test_send_periodic_disabled(self):
        self.event.settings.set('waiting_list_enabled', True)
        self.event.settings.set('waiting_list_auto', False)
        for i in range(5):
            WaitingListEntry.objects.create(
                event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
            )
        process_waitinglist(None)
        assert WaitingListEntry.objects.filter(voucher__isnull=True).count() == 5
        assert Voucher.objects.count() == 0

    def test_send_periodic_disabled2(self):
        self.event.settings.set('waiting_list_enabled', False)
        self.event.settings.set('waiting_list_auto', True)
        for i in range(5):
            WaitingListEntry.objects.create(
                event=self.event, item=self.item2, variation=self.var1, email='foo{}@bar.com'.format(i)
            )
        process_waitinglist(None)
        assert Voucher.objects.count() == 5
