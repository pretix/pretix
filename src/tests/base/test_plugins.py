from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.base.plugins import get_all_plugins
from pretix.base.signals import register_ticket_outputs


class PluginRegistryTest(TestCase):
    """
    This test case performs tests for the plugin registry.
    """

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_plugin_names(self):
        for mod in get_all_plugins():
            self.assertIn(mod.module, settings.INSTALLED_APPS)

    def test_metadata(self):
        for mod in get_all_plugins():
            self.assertTrue(hasattr(mod, 'name'))
            self.assertTrue(hasattr(mod, 'version'))
            self.assertTrue(hasattr(mod, 'type'))


class PluginSignalTest(TestCase):
    """
    This test case tests the EventPluginSignal handler
    """
    @classmethod
    def setUpTestData(cls):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        cls.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_no_plugins_active(self):
        self.event.plugins = ''
        self.event.save()
        responses = register_ticket_outputs.send(self.event)
        self.assertEqual(len(responses), 0)

    def test_one_plugin_active(self):
        self.event.plugins = 'tests.testdummy'
        self.event.save()
        payload = {'foo': 'bar'}
        responses = register_ticket_outputs.send(self.event, **payload)
        self.assertEqual(len(responses), 1)
        self.assertIn('tests.testdummy.signals', [r[0].__module__ for r in responses])
