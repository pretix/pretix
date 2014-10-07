from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now

from tixlbase.models import (
    Event, Organizer, Item, Property, PropertyValue, ItemVariation
)

# Do NOT use relative imports here
from tixlplugins.timerestriction import signals
from tixlplugins.timerestriction.models import TimeRestriction


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
        r.items.add(self.item)
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
        r.items.add(self.item)
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
        r.items.add(self.item)
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
        r1.items.add(self.item)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=3),
            timeframe_to=now() + timedelta(days=5),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
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
        r1.items.add(self.item)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=1),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
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
        r1.items.add(self.item)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=4),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
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
        r1.items.add(self.item)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() + timedelta(days=4),
            timeframe_to=now() + timedelta(days=7),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
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
        v1 = ItemVariation.objects.create(item=self.item)
        v1.values.add(self.value1)
        v2 = ItemVariation.objects.create(item=self.item)
        v2.values.add(self.value2)

        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.items.add(self.item)
        r1.variations.add(v1)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 3)
        for v in result:
            if 'variation' in v and v['variation'].pk == v1.pk:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 12)
            else:
                self.assertFalse(v['available'])

    def test_variation_specific_and_general(self):
        self.item.properties.add(self.property)
        v1 = ItemVariation.objects.create(item=self.item)
        v1.values.add(self.value1)
        v2 = ItemVariation.objects.create(item=self.item)
        v2.values.add(self.value2)

        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.items.add(self.item)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
        r2.variations.add(v1)
        r3 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() - timedelta(days=1),
            event=self.event,
            price=10
        )
        r3.items.add(self.item)
        r3.variations.add(v2)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 3)
        for v in result:
            if 'variation' in v and v['variation'].pk == v1.pk:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 8)
            else:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 12)

    def test_variation_specifics(self):
        self.item.properties.add(self.property)
        v1 = ItemVariation.objects.create(item=self.item)
        v1.values.add(self.value1)
        v2 = ItemVariation.objects.create(item=self.item)
        v2.values.add(self.value2)

        r1 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=12
        )
        r1.items.add(self.item)
        r1.variations.add(v1)
        r2 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() + timedelta(days=1),
            event=self.event,
            price=8
        )
        r2.items.add(self.item)
        r2.variations.add(v1)
        r3 = TimeRestriction.objects.create(
            timeframe_from=now() - timedelta(days=5),
            timeframe_to=now() - timedelta(days=1),
            event=self.event,
            price=8
        )
        r3.items.add(self.item)
        r3.variations.add(v2)
        result = signals.availability_handler(
            self.event, item=self.item,
            variations=self.item.get_all_variations(),
            context=None, cache=self.event.get_cache()
        )
        self.assertEqual(len(result), 3)
        for v in result:
            if 'variation' in v and v['variation'].pk == v1.pk:
                self.assertTrue(v['available'])
                self.assertEqual(v['price'], 8)
            else:
                self.assertFalse(v['available'])
