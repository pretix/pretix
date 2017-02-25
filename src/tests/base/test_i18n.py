from django.test import TestCase
from django.utils import translation
from django.utils.timezone import now
from i18nfield.strings import LazyI18nString

from pretix.base.models import Event, ItemCategory, Organizer


class I18nStringTest(TestCase):
    """
    This test case tests the LazyI18nString class
    """

    def test_explicit_translation(self):
        data = {
            'de': 'Hallo',
            'en': 'Hello'
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hallo')

    def test_similar_translations(self):
        data = {
            'en': 'You',
            'de': 'Sie',
            'de-informal': 'Du'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Sie')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Du')

        data = {
            'en': 'You',
            'de-informal': 'Du'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Du')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Du')

        data = {
            'en': 'You',
            'de': 'Sie'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Sie')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Sie')

    def test_missing_default_translation(self):
        data = {
            'de': 'Hallo',
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hallo')
        translation.activate('de')
        self.assertEqual(str(s), 'Hallo')

    def test_missing_translation(self):
        data = {
            'en': 'Hello',
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hello')

    def test_legacy_string(self):
        s = LazyI18nString("Hello")
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hello')

    def test_none(self):
        s = LazyI18nString(None)
        self.assertEqual(str(s), "")
        s = LazyI18nString("")
        self.assertEqual(str(s), "")


class I18nFieldTest(TestCase):
    """
    This test case tests the I18n*Field classes
    """
    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_save_load_cycle_plain_string(self):
        obj = ItemCategory.objects.create(event=self.event, name="Hello")
        obj = ItemCategory.objects.get(id=obj.id)
        self.assertIsInstance(obj.name, LazyI18nString)
        translation.activate('en')
        self.assertEqual(str(obj.name), "Hello")
        translation.activate('de')
        self.assertEqual(str(obj.name), "Hello")

    def test_save_load_cycle_i18n_string(self):
        obj = ItemCategory.objects.create(event=self.event,
                                          name=LazyI18nString(
                                              {
                                                  'de': 'Hallo',
                                                  'en': 'Hello'
                                              }
                                          ))
        obj = ItemCategory.objects.get(id=obj.id)
        self.assertIsInstance(obj.name, LazyI18nString)
        translation.activate('en')
        self.assertEqual(str(obj.name), "Hello")
        translation.activate('de')
        self.assertEqual(str(obj.name), "Hallo")
