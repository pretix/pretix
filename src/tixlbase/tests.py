from django.test import TestCase
from django.utils.timezone import now

from tixlbase.models import (
    Event, Organizer, Item, ItemVariation,
    Property, PropertyValue
)


class ItemVariationsTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        e = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        p = Property.objects.create(event=e, name='Size')
        PropertyValue.objects.create(prop=p, value='S')
        PropertyValue.objects.create(prop=p, value='M')
        PropertyValue.objects.create(prop=p, value='L')
        p = Property.objects.create(event=e, name='Color')
        PropertyValue.objects.create(prop=p, value='black')
        PropertyValue.objects.create(prop=p, value='blue')

    def test_get_all_variations(self):
        e = Event.objects.get(name='Dummy', organizer__name='Dummy')
        i = Item.objects.create(event=e, name='Dummy')

        # No properties available
        v = i.get_all_variations()
        self.assertEqual(len(v), 0)

        # One property, no variations
        p = Property.objects.get(event=e, name='Size')
        i.properties.add(p)
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        for var in v:
            self.assertIs(type(var), tuple)
            self.assertIs(type(var[0]), PropertyValue)
            values.append(var[0].value)
        self.assertEqual(sorted(values), sorted(['S', 'M', 'L']))

        # One property, one variation
        iv = ItemVariation.objects.create(item=i)
        iv.values.add(PropertyValue.objects.get(prop=p, value='S'))
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 3)
        values = []
        for var in v:
            if type(var) == ItemVariation:
                self.assertEqual(iv.pk, var.pk)
                values.append(iv.values.all()[0].value)
            elif type(var) == tuple:
                self.assertIs(type(var[0]), PropertyValue)
                values.append(var[0].value)
        self.assertEqual(sorted(values), sorted(['S', 'M', 'L']))

        # Two properties, one variation
        p2 = Property.objects.get(event=e, name='Color')
        i.properties.add(p2)
        iv.values.add(PropertyValue.objects.get(prop=p2, value='black'))
        v = i.get_all_variations()
        self.assertIs(type(v), list)
        self.assertEqual(len(v), 6)
        values = []
        num_variations = 0
        for var in v:
            if type(var) == ItemVariation:
                self.assertEqual(iv.pk, var.pk)
                values.append(sorted([ivv.value for ivv in iv.values.all()]))
                self.assertEqual(sorted([ivv.value for ivv in iv.values.all()]), sorted(['S', 'black']))
                num_variations += 1
            elif type(var) == tuple:
                values.append(sorted([pv.value for pv in var]))
        self.assertEqual(sorted(values), sorted([
            ['S', 'black'],
            ['S', 'blue'],
            ['M', 'black'],
            ['M', 'blue'],
            ['L', 'black'],
            ['L', 'blue'],
        ]))
        self.assertEqual(num_variations, 1)
