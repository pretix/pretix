import datetime

from tests.base import BrowserTest

from pretix.base.models import (
    Event, EventPermission, Organizer, OrganizerPermission, User,
)


class EventsTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.event2 = Event.objects.create(
            organizer=self.orga1, name='31C3', slug='31c3',
            date_from=datetime.datetime(2014, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.event3 = Event.objects.create(
            organizer=self.orga2, name='MRMCD14', slug='mrmcd14',
            date_from=datetime.datetime(2014, 9, 5, tzinfo=datetime.timezone.utc),
        )
        self.event4 = Event.objects.create(
            organizer=self.orga2, name='MRMCD00', slug='mrmcd00',
            date_from=datetime.datetime(2000, 9, 5, tzinfo=datetime.timezone.utc),
        )
        self.event4.delete()
        OrganizerPermission.objects.create(organizer=self.orga1, user=self.user)
        EventPermission.objects.create(event=self.event1, user=self.user, can_change_items=True,
                                       can_change_settings=True)
        EventPermission.objects.create(event=self.event4, user=self.user, can_change_items=True,
                                       can_change_settings=True)
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('dummy')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("navbar-right")

    def test_event_list(self):
        self.driver.get('%s%s' % (self.live_server_url, '/control/events/'))
        tabletext = self.driver.find_element_by_css_selector("#page-wrapper .table").text
        self.assertIn("30C3", tabletext)
        self.assertNotIn("31C3", tabletext)
        self.assertNotIn("MRMCD14", tabletext)
        self.assertNotIn("MRMCD00", tabletext)

    def test_settings(self):
        self.driver.get('%s/control/event/%s/%s/settings/' % (self.live_server_url, self.orga1.slug,
                                                              self.event1.slug))
        self.driver.find_element_by_name("date_to").send_keys("2013-12-30 17:00:00")
        self.driver.find_element_by_name("settings-mail_prefix").send_keys("TEST")
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("2013-12-30 17:00:00", self.driver.find_element_by_name("date_to").get_attribute("value"))
        self.assertIn("TEST", self.driver.find_element_by_name("settings-mail_prefix").get_attribute("value"))

    def test_plugins(self):
        self.driver.get('%s/control/event/%s/%s/settings/plugins' % (self.live_server_url, self.orga1.slug,
                                                                     self.event1.slug))
        self.assertIn("Restriction by time", self.driver.find_element_by_class_name("form-plugins").text)
        self.assertIn("Enable", self.driver.find_element_by_name("plugin:pretix.plugins.timerestriction").text)
        self.driver.find_element_by_name("plugin:pretix.plugins.timerestriction").click()
        self.assertIn("Disable", self.driver.find_element_by_name("plugin:pretix.plugins.timerestriction").text)
        self.driver.find_element_by_name("plugin:pretix.plugins.timerestriction").click()
        self.assertIn("Enable", self.driver.find_element_by_name("plugin:pretix.plugins.timerestriction").text)
