import time
import datetime
from selenium.webdriver.support.select import Select
from tixlbase.models import User, Organizer, Event, OrganizerPermission, EventPermission, ItemCategory, Property, \
    PropertyValue, Question, Quota, Item
from tixlbase.tests import BrowserTest, on_platforms


class ItemFormTest(BrowserTest):
    def setUp(self):
        super().setUp()
        self.driver.set_window_size(1920, 1080)
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

    def scroll_into_view(self, element):
        """Scroll element into view"""
        y = element.location['y']
        self.driver.execute_script('window.scrollTo(0, {0})'.format(y))

    def scroll_and_click(self, element):
        self.scroll_into_view(element)
        time.sleep(0.5)
        element.click()


@on_platforms()
class CategoriesTest(ItemFormTest):

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
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("T-Shirts", self.driver.find_element_by_css_selector(".container table").text)
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector(".container table").text)

    def test_sort(self):
        ItemCategory.objects.create(event=self.event1, name="Entry tickets", position=0)
        ItemCategory.objects.create(event=self.event1, name="T-Shirts", position=1)
        self.driver.get('%s/control/event/%s/%s/categories/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.assertIn("Entry tickets",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(1)").text)
        self.assertIn("T-Shirts",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(2)").text)
        self.scroll_and_click(self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(1) a[href*='down']"))
        time.sleep(1)
        self.assertIn("Entry tickets",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(2)").text)
        self.assertIn("T-Shirts",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(1)").text)
        self.scroll_and_click(self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(2) a[href*='up']"))
        time.sleep(1)
        self.assertIn("Entry tickets",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(1)").text)
        self.assertIn("T-Shirts",
                      self.driver.find_element_by_css_selector("table > tbody > tr:nth-child(2)").text)

    def test_delete(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        self.driver.get('%s/control/event/%s/%s/categories/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector(".container table").text)


@on_platforms()
class PropertiesTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/properties/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_css_selector("#id_name").send_keys('Size')
        self.driver.find_element_by_name("values-0-value").send_keys('S')
        self.driver.find_element_by_name("values-1-value").send_keys('M')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
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
        self.scroll_into_view(self.driver.find_element_by_name("values-1-value"))
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


@on_platforms()
class QuestionsTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/questions/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("question").send_keys('What is your shoe size?')
        Select(self.driver.find_element_by_name("type")).select_by_value('N')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("shoe size", self.driver.find_element_by_css_selector(".container table").text)

    def test_update(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        self.driver.get('%s/control/event/%s/%s/questions/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("question").clear()
        self.driver.find_element_by_name("question").send_keys('How old are you?')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("How old", self.driver.find_element_by_css_selector(".container table").text)
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector(".container table").text)
        c = Question.objects.current.get(identity=c.identity)
        self.assertTrue(c.required)

    def test_delete(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        self.driver.get('%s/control/event/%s/%s/questions/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector(".container table").text)


@on_platforms()
class QuotaTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/quotas/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("name").send_keys('Full house')
        self.driver.find_element_by_name("size").send_keys('500')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Full house", self.driver.find_element_by_css_selector(".container table").text)

    def test_update(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        item1 = Item.objects.create(event=self.event1, name="Standard")
        item2 = Item.objects.create(event=self.event1, name="Business")
        prop1 = Property.objects.create(event=self.event1, name="Level")
        item2.properties.add(prop1)
        PropertyValue.objects.create(prop=prop1, value="Silver")
        PropertyValue.objects.create(prop=prop1, value="Gold")
        self.driver.get('%s/control/event/%s/%s/quotas/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("size").clear()
        self.driver.find_element_by_name("size").send_keys('350')
        self.scroll_and_click(self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(1) .panel-title a'))
        time.sleep(1)
        self.scroll_and_click(self.driver.find_element_by_name("item_%s" % item1.identity))
        self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(2) .panel-title a').click()
        time.sleep(1)
        self.scroll_and_click(self.driver.find_elements_by_css_selector("input[name=item_%s]" % item2.identity)[1])
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("350", self.driver.find_element_by_css_selector(".container table").text)
        self.assertNotIn("500", self.driver.find_element_by_css_selector(".container table").text)

    def test_delete(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        self.driver.get('%s/control/event/%s/%s/quotas/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Full house", self.driver.find_element_by_css_selector(".container table").text)
