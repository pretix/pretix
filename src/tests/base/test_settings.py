from datetime import datetime, time, date
from decimal import Decimal
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import Event, Organizer, User
from pretix.base import settings
from pretix.base.settings import SettingsSandbox


class SettingsTestCase(TestCase):

    def setUp(self):
        settings.DEFAULTS['test_default'] = 'def'
        self.organizer = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=self.organizer, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_event_set_explicit(self):
        self.event.settings.test = 'foo'
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.event = Event.objects.get(identity=self.event.identity)
        self.assertEqual(self.event.settings.test, 'foo')

    def test_event_set_twice(self):
        self.event.settings.test = 'bar'
        self.event.settings.test = 'foo'
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.event = Event.objects.get(identity=self.event.identity)
        self.assertEqual(self.event.settings.test, 'foo')

    def test_event_set_on_organizer(self):
        self.organizer.settings.test = 'foo'
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'foo')

        # Reload object
        self.organizer = Organizer.objects.get(identity=self.organizer.identity)
        self.event = Event.objects.get(identity=self.event.identity)
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'foo')

    def test_override_organizer(self):
        self.organizer.settings.test = 'foo'
        self.event.settings.test = 'bar'
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'bar')

        # Reload object
        self.organizer = Organizer.objects.get(identity=self.organizer.identity)
        self.event = Event.objects.get(identity=self.event.identity)
        self.assertEqual(self.organizer.settings.test, 'foo')
        self.assertEqual(self.event.settings.test, 'bar')

    def test_default(self):
        self.assertEqual(self.organizer.settings.test_default, 'def')
        self.assertEqual(self.event.settings.test_default, 'def')
        self.assertEqual(self.event.settings.get('nonexistant', default='abc'), 'abc')

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

        self.event = Event.objects.get(identity=self.event.identity)
        self.assertEqual(self.event.settings.test, 'foo')

        del self.organizer.settings.test
        self.assertIsNone(self.organizer.settings.test)

        self.organizer = Organizer.objects.get(identity=self.organizer.identity)
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

    def test_serialize_bool(self):
        self._test_serialization(True, bool)
        self._test_serialization(False, bool)

    def test_serialize_versionable(self):
        self._test_serialization(self.event, Event)

    def test_serialize_model(self):
        self._test_serialization(User.objects.create_local_user(self.event, 'dummy', 'dummy'), User)

    def test_serialize_unknown(self):
        class Type:
            pass
        try:
            self._test_serialization(Type(), Type)
            self.assertTrue(False, 'No exception thrown!')
        except TypeError:
            pass

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

        self.event = Event.objects.get(identity=self.event.identity)
        sandbox = SettingsSandbox('testing', 'foo', self.event)
        self.assertEqual(sandbox['bar'], 'baz')
        self.assertEqual(sandbox.baz, '42')

        del sandbox.baz
        del sandbox['bar']

        self.assertIsNone(sandbox.bar)
        self.assertIsNone(sandbox['baz'])
