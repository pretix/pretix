import pytest
from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.base.plugins import get_all_plugins
from pretix.base.signals import register_ticket_outputs

plugins = get_all_plugins()


@pytest.mark.django_db
@pytest.mark.parametrize("plugin", plugins)
def test_metadata(plugin):
    assert hasattr(plugin, 'name')
    assert hasattr(plugin, 'version')


@pytest.mark.django_db
@pytest.mark.parametrize("plugin", plugins)
def test_plugin_installed(plugin):
    assert plugin.module in settings.INSTALLED_APPS


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
