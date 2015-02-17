from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    Event, Organizer, Item, Property, PropertyValue, ItemVariation
)

# Do NOT use relative imports here
from pretix.plugins.timerestriction import signals
from pretix.plugins.timerestriction.models import TimeRestriction


class TimeRestrictionTest(TestCase):
    """
    This test case tests the various aspects of the time restriction
    plugin
    """

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        self.item = Item.objects.create(event=self.event, name='Dummy', default_price=14)
        self.property = Property.objects.create(event=self.event, name='Size')
        self.value1 = PropertyValue.objects.create(prop=self.property, value='S')
        self.value2 = PropertyValue.objects.create(prop=self.property, value='M')
        self.value3 = PropertyValue.objects.create(prop=self.property, value='L')
        self.variation1 = ItemVariation.objects.create(item=self.item)
        self.variation1.values.add(self.value1)
        self.variation2 = ItemVariation.objects.create(item=self.item)
        self.variation2.values.add(self.value2)
        self.variation3 = ItemVariation.objects.create(item=self.item)
        self.variation3.values.add(self.value3)

    def test_nothing(self):
        result = signals.availability_handler(
            None, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertTrue('available' not in result[0] or result[0]['available'] is True)

    def test_simple_case_available(self):
        r = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=3),
            timeframe_to=now() + timedelta(days=3),
            event=self.event,
            price=12
        )
        r.item = self.item
        r.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 12)

    def test_cached_result(self):
        r = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=3),
            timeframe_to=now() + timedelta(days=3),
            event=self.event,
            price=12
        )
        r.item = self.item
        r.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 12)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 12)

    def test_simple_case_unavailable(self):
        r = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() - timedelta(days=3),
            event=self.event,
            price=12
        )
        r.item = self.item
        r.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertFalse(result[0]['available'])

    def test_multiple_overlapping_now(self):
        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=3),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=3),
            timeframe_to=now() + timedelta(days=5),
            event=self.event,
            price=8
        )
        r2.item = self.item
        r2.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 8)

    def test_multiple_overlapping_tomorrow(self):
        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=5),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=1),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.item = self.item
        r2.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 12)

    def test_multiple_distinct_available(self):
        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=2),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=4),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.item = self.item
        r2.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertTrue(result[0]['available'])
        self.assertEqual(result[0]['price'], 12)

    def test_multiple_distinct_unavailable(self):
        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() - timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=4),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.item = self.item
        r2.save()
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 1)
        self.assertIn('available', result[0])
        self.assertFalse(result[0]['available'])

    def test_variation_specific(self):
        self.item.properties.add(self.property)

        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r1.variations.add(self.variation1)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 3)
        for v in result:
            if 'variation' in v and v['variation'].pk == self.variation1.pk:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 12)
            else:
                self.assertFalse(v['available'])

    def test_variation_specifics(self):
        self.item.properties.add(self.property)

        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.item = self.item
        r1.save()
        r1.variations.add(self.variation1)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=8
        )
        r2.item = self.item
        r2.save()
        r2.variations.add(self.variation1)
        r3 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() - timedelta(days=1),
            event=self.event,
            price=8
        )
        r3.item = self.item
        r3.save()
        r3.variations.add(self.variation3)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 3)
        for v in result:
            if 'variation' in v and v['variation'].pk == self.variation1.pk:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 8)
            else:
                self.assertFalse(v['available'])
