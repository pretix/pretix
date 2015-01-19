from django.test import TestCase
from django.utils.timezone import now

from pretixbase.models import (
    Event, Organizer, Item, ItemVariation,
    Property, PropertyValue, User
)
from pretixbase.types import VariationDict


class ItemVariationsTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        p = Property.objects.create(event=self.event, name='Size')
        PropertyValue.objects.create(prop=p, value='S')
        PropertyValue.objects.create(prop=p, value='M')
        PropertyValue.objects.create(prop=p, value='L')
        p = Property.objects.create(event=self.event, name='Color')
        PropertyValue.objects.create(prop=p, value='black')
        PropertyValue.objects.create(prop=p, value='blue')

    def test_variationdict(self):
        i = Item.objects.create(event=self.event, name='Dummy')
        p = Property.objects.get(event=self.event, name='Size')
        i.properties.add(p)
        iv = ItemVariation.objects.create(item=i)
        pv = PropertyValue.objects.get(prop=p, value='S')
        iv.values.add(pv)

        variations = i.get_all_variations()

        for vd in variations:
            for i, v in vd.relevant_items():
                self.assertIs(type(v), PropertyValue)

            for v in vd.relevant_values():
                self.assertIs(type(v), PropertyValue)

            if vd[p.pk] == pv:
                vd1 = vd

        vd2 = VariationDict()
        vd2[p.pk] = pv

        self.assertEqual(vd2.identify(), vd1.identify())
        self.assertEqual(vd2, vd1)

        vd2[p.pk] = PropertyValue.objects.get(prop=p, value='M')

        self.assertNotEqual(vd2.identify(), vd.identify())
        self.assertNotEqual(vd2, vd1)

        vd3 = vd2.copy()
        self.assertEqual(vd3, vd2)

        vd2[p.pk] = pv
        self.assertNotEqual(vd3, vd2)

        vd4 = VariationDict()
        vd4[4] = 'b'
        vd4[2] = 'a'
        self.assertEqual(vd4.ordered_values(), ['a', 'b'])

    def test_get_all_variations(self):
        i = Item.objects.create(event=self.event, name='Dummy')

        # No properties available
        v = i.get_all_variations()
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0], {})

        # One property, no variations
        p = Property.objects.get(event=self.event, name='Size')
        i.properties.add(p)
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        for var in v:
            self.assertIs(type(var), VariationDict)
            self.assertIn(p.pk, var)
            self.assertIs(type(var[p.pk]), PropertyValue)
            values.append(var[p.pk].value)
        self.assertEqual(sorted(values), sorted(['S', 'M', 'L']))

        # One property, one variation
        iv = ItemVariation.objects.create(item=i)
        iv.values.add(PropertyValue.objects.get(prop=p, value='S'))
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        num_variations = 0
        for var in v:
            self.assertIs(type(var), VariationDict)
            if 'variation' in var and type(var['variation']) is ItemVariation:
                self.assertEqual(iv.pk, var['variation'].pk)
                values.append(var['variation'].values.all()[0].value)
                num_variations += 1
            elif p.pk in var:
                self.assertIs(type(var[p.pk]), PropertyValue)
                values.append(var[p.pk].value)
        self.assertEqual(sorted(values), sorted(['S', 'M', 'L']))
        self.assertEqual(num_variations, 1)

        # Two properties, one variation
        p2 = Property.objects.get(event=self.event, name='Color')
        i.properties.add(p2)
        iv.values.add(PropertyValue.objects.get(prop=p2, value='black'))
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 6)
        values = []
        num_variations = 0
        for var in v:
            self.assertIs(type(var), VariationDict)
            if 'variation' in var:
                self.assertEqual(iv.pk, var['variation'].pk)
                values.append(sorted([ivv.value for ivv in iv.values.all()]))
                self.assertEqual(sorted([ivv.value for ivv in iv.values.all()]), sorted(['S', 'black']))
                num_variations += 1
            else:
                values.append(sorted([pv.value for pv in var.values()]))
        self.assertEqual(sorted(values), sorted([
            ['S', 'black'],
            ['S', 'blue'],
            ['M', 'black'],
            ['M', 'blue'],
            ['L', 'black'],
            ['L', 'blue'],
        ]))
        self.assertEqual(num_variations, 1)


class VersionableTestCase(TestCase):

    def test_shallow_cone(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        old = Item.objects.create(event=event, name='Dummy', default_price=14)
        prop = Property.objects.create(event=event, name='Size')
        old.properties.add(prop)
        new = old.clone_shallow()
        self.assertIsNone(new.version_end_date)
        self.assertIsNotNone(old.version_end_date)
        self.assertEqual(new.properties.count(), 0)
        self.assertEqual(old.properties.count(), 1)


class UserTestCase(TestCase):

    def test_identifier_local(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        u = User(event=event, username='tester')
        u.set_password("test")
        u.save()
        self.assertEqual(u.identifier, "%s@%s.event.pretix" % (u.username.lower(), event.id))

    def test_identifier_global(self):
        u = User(email='test@example.com')
        u.set_password("test")
        u.save()
        self.assertEqual(u.identifier, "test@example.com")
