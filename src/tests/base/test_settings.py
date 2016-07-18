from datetime import date, datetime, time
from decimal import Decimal

from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils.timezone import now

from pretix.base import settings
from pretix.base.i18n import LazyI18nString
from pretix.base.models import Event, Organizer, User
from pretix.base.settings import SettingsSandbox


class SettingsTestCase(TestCase):
    def setUp(self):
        settings.DEFAULTS['test_default'] = {
            'default': 'def',
            'type': str
        }
        self.organizer = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=self.organizer, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_organizer_set_explicit(self):
        self.organizer.settings.test = 'foo'
        self.assertEqual(self.organizer.settings.test, 'foo')

        # Reload object
        self.organizer = Organizer.objects.get(id=self.organizer.id)
        self.assertEqual(self.organizer.settings.test, 'foo')

    def test_event_set_explicit(self):
        self.event.settings.test = 'foo'
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.event = Event.objects.get(id=self.event.id)
        self.assertEqual(self.event.settings.test, 'foo')

    def test_event_set_twice(self):
        self.event.settings.test = 'bar'
        self.event.settings.test = 'foo'
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.event = Event.objects.get(id=self.event.id)
        self.assertEqual(self.event.settings.test, 'foo')

    def test_event_set_on_organizer(self):
        self.organizer.settings.test = 'foo'
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.organizer = Organizer.objects.get(id=self.organizer.id)

    def test_override_organizer(self):
        self.organizer.settings.test = 'foo'
        self.event.settings.test = 'bar'
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'bar')

        # Reload object
        self.organizer = Organizer.objects.get(id=self.organizer.id)
        self.event = Event.objects.get(id=self.event.id)
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'bar')

    def test_default(self):
        self.assertEqual(self.organizer.settings.test_default, 'def')
        self.assertEqual(self.event.settings.test_default, 'def')
        self.assertEqual(self.event.settings.get('nonexistant', default='abc'), 'abc')

    def test_default_typing(self):
        self.assertIs(type(self.event.settings.get('nonexistant', as_type=Decimal, default=0)), Decimal)

    def test_item_access(self):
        self.event.settings['foo'] = 'abc'
        self.assertEqual(self.event.settings['foo'], 'abc')
        del self.event.settings['foo']
        self.assertIsNone(self.event.settings['foo'])

    def test_delete(self):
        self.organizer.settings.test = 'foo'
        self.event.settings.test = 'bar'
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'bar')

        del self.event.settings.test
        self.assertEqual(self.event.settings.test, 'foo')

        self.event = Event.objects.get(id=self.event.id)
        self.assertEqual(self.event.settings.test, 'foo')

        del self.organizer.settings.test
        self.assertIsNone(self.organizer.settings.test)

        self.organizer = Organizer.objects.get(id=self.organizer.id)
        self.assertIsNone(self.organizer.settings.test)

    def test_serialize_str(self):
        self._test_serialization('ABC', as_type=str)

    def test_serialize_float(self):
        self._test_serialization(2.3, float)

    def test_serialize_int(self):
        self._test_serialization(2, int)

    def test_serialize_datetime(self):
        self._test_serialization(now(), datetime)

    def test_serialize_time(self):
        self._test_serialization(now().time(), time)

    def test_serialize_date(self):
        self._test_serialization(now().date(), date)

    def test_serialize_decimal(self):
        self._test_serialization(Decimal('2.3'), Decimal)

    def test_serialize_dict(self):
        self._test_serialization({'a': 'b', 'c': 'd'}, dict)

    def test_serialize_list(self):
        self._test_serialization([1, 2, 'a'], list)

    def test_serialize_lazyi18nstring(self):
        self._test_serialization(LazyI18nString({'de': 'Hallo', 'en': 'Hello'}), LazyI18nString)

    def test_serialize_bool(self):
        self._test_serialization(True, bool)
        self._test_serialization(False, bool)

    def test_serialize_bool_implicit(self):
        self.event.settings.set('test', True)
        self.event.settings._flush()
        self.assertIs(self.event.settings.get('test', as_type=None), True)
        self.event.settings.set('test', False)
        self.event.settings._flush()
        self.assertIs(self.event.settings.get('test', as_type=None), False)

    def test_serialize_versionable(self):
        self._test_serialization(self.event, Event)

    def test_serialize_model(self):
        self._test_serialization(User.objects.create_user('dummy@dummy.dummy', 'dummy'), User)

    def test_serialize_unknown(self):
        class Type:
            pass

        try:
            self._test_serialization(Type(), Type)
            self.assertTrue(False, 'No exception thrown!')
        except TypeError:
            pass

    def test_serialize_file(self):
        val = SimpleUploadedFile("sample_invalid_image.jpg", b"file_content", content_type="image/jpeg")
        self.event.settings.set('test', val)
        self.event.settings._flush()
        self.assertIsInstance(self.event.settings.get('test', as_type=File), File)
        self.assertTrue(self.event.settings.get('test', as_type=File).name.endswith(val.name))

    def test_detect_file_value(self):
        val = SimpleUploadedFile("sample_invalid_image.jpg", b"file_content", content_type="image/jpeg")
        self.event.settings.set('test', val)
        self.event.settings._flush()
        self.assertIsInstance(self.event.settings.get('test'), File)
        self.assertTrue(self.event.settings.get('test').name.endswith(val.name))

    def _test_serialization(self, val, as_type):
        self.event.settings.set('test', val)
        self.event.settings._flush()
        self.assertEqual(self.event.settings.get('test', as_type=as_type), val)
        self.assertIsInstance(self.event.settings.get('test', as_type=as_type), as_type)

    def test_sandbox(self):
        sandbox = SettingsSandbox('testing', 'foo', self.event)
        sandbox.set('foo', 'bar')
        self.assertEqual(sandbox.get('foo'), 'bar')
        self.assertEqual(self.event.settings.get('testing_foo_foo'), 'bar')
        self.assertIsNone(self.event.settings.get('foo'), 'bar')

        sandbox['bar'] = 'baz'
        sandbox.baz = 42

        self.event = Event.objects.get(id=self.event.id)
        sandbox = SettingsSandbox('testing', 'foo', self.event)
        self.assertEqual(sandbox['bar'], 'baz')
        self.assertEqual(sandbox.baz, '42')

        del sandbox.baz
        del sandbox['bar']

        self.assertIsNone(sandbox.bar)
        self.assertIsNone(sandbox['baz'])

    def test_freeze(self):
        olddef = settings.DEFAULTS
        settings.DEFAULTS = {
            'test_default': {
                'default': 'def',
                'type': str
            }
        }
        self.event.organizer.settings.set('bar', 'baz')
        self.event.organizer.settings.set('foo', 'baz')
        self.event.settings.set('foo', 'bar')
        try:
            self.assertEqual(self.event.settings.freeze(), {
                'test_default': 'def',
                'bar': 'baz',
                'foo': 'bar'
            })
        finally:
            settings.DEFAULTS = olddef
