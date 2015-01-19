from django.test import TestCase
from django.utils.timezone import now
from django.conf import settings

from pretixbase.models import Event, Organizer
from pretixbase.plugins import get_all_plugins
from pretixbase.signals import determine_availability


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

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_no_plugins_active(self):
        self.event.plugins = ''
        self.event.save()
        responses = determine_availability.send(self.event)
        self.assertEqual(len(responses), 0)

    def test_one_plugin_active(self):
        self.event.plugins = 'pretixplugins.testdummy'
        self.event.save()
        payload = {'foo': 'bar'}
        responses = determine_availability.send(self.event, **payload)
        self.assertEqual(len(responses), 1)
        self.assertIn('pretixplugins.testdummy.signals', [r[0].__module__ for r in responses])
