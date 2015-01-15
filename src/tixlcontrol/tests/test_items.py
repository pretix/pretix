import datetime
from tixlbase.models import User, Organizer, Event, OrganizerPermission, EventPermission, ItemCategory, Property, \
    PropertyValue
from tixlbase.tests import BrowserTest, on_platforms


@on_platforms()
class CategoriesTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        OrganizerPermission.objects.create(organizer=self.orga1, user=self.user)
        EventPermission.objects.create(event=self.event1, user=self.user, can_change_items=True,
                                       can_change_settings=True)
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('dummy')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("navbar-right")

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/categories/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("name").send_keys('Entry tickets')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Entry tickets", self.driver.find_element_by_css_selector(".container table").text)

    def test_update(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        self.driver.get('%s/control/event/%s/%s/categories/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("name").clear()
        self.driver.find_element_by_name("name").send_keys('T-Shirts')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("T-Shirts", self.driver.find_element_by_css_selector(".container table").text)
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector(".container table").text)

    def test_delete(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        self.driver.get('%s/control/event/%s/%s/categories/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector(".container table").text)


@on_platforms()
class PropertiesTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            )
        OrganizerPermission.objects.create(organizer=self.orga1, user=self.user)
        EventPermission.objects.create(event=self.event1, user=self.user, can_change_items=True,
                                       can_change_settings=True)
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('dummy')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("navbar-right")

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/properties/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_css_selector("#id_name").send_keys('Size')
        self.driver.find_element_by_name("values-0-value").send_keys('S')
        self.driver.find_element_by_name("values-1-value").send_keys('M')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Size", self.driver.find_element_by_css_selector(".container table").text)
        self.driver.find_element_by_partial_link_text("Size").click()
        self.assertEqual("S", self.driver.find_element_by_name("values-0-value").get_attribute("value"))
        self.assertEqual("M", self.driver.find_element_by_name("values-1-value").get_attribute("value"))

    def test_update(self):
        c = Property.objects.create(event=self.event1, name="Size")
        PropertyValue.objects.create(prop=c, position=0, value="S")
        PropertyValue.objects.create(prop=c, position=1, value="M")
        self.driver.get('%s/control/event/%s/%s/properties/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_css_selector("#id_name").clear()
        self.driver.find_element_by_css_selector("#id_name").send_keys('Color')
        self.driver.find_elements_by_css_selector("div.form-group button.btn-danger")[0].click()
        self.driver.find_element_by_name("values-1-value").clear()
        self.driver.find_element_by_name("values-1-value").send_keys('red')
        self.driver.find_element_by_css_selector("button[data-formset-add]").click()
        self.driver.find_element_by_name("values-2-value").send_keys('blue')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertEqual("red", self.driver.find_element_by_name("values-0-value").get_attribute("value"))
        self.assertEqual("blue", self.driver.find_element_by_name("values-1-value").get_attribute("value"))

    def test_delete(self):
        c = Property.objects.create(event=self.event1, name="Size")
        self.driver.get('%s/control/event/%s/%s/properties/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Size", self.driver.find_element_by_css_selector(".container table").text)
