import datetime
import os
import time
import unittest

from django.utils.timezone import now
from selenium.webdriver.support.select import Select
from tests.base import BrowserTest

from pretix.base.models import (
    Event, EventPermission, Item, ItemCategory, Organizer, OrganizerPermission,
    Property, PropertyValue, Question, Quota, User,
)


class ItemFormTest(BrowserTest):
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


class CategoriesTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/categories/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("name_0").send_keys('Entry tickets')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Entry tickets", self.driver.find_element_by_css_selector("#page-wrapper table").text)

    def test_update(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/categories/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("name_0").clear()
        self.driver.find_element_by_name("name_0").send_keys('T-Shirts')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("T-Shirts", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert str(ItemCategory.objects.as_of(t1).get(identity=c.identity).name) == 'Entry tickets'
        assert str(ItemCategory.objects.current.get(identity=c.identity).name) == 'T-Shirts'

    @unittest.skipIf('TRAVIS' in os.environ, 'See docstring for details.')
    def test_sort(self):
        """
        For unknown reasons, the first scoll_and_click() call sometimes results in the following exception

        selenium.common.exceptions.ElementNotVisibleException:
        Message: {"errorMessage":"Element is not currently visible and may not be manipulated", …}

        This exception does not occur on either of my machines, but only when being run in Travis CI.

        – Raphael Michel, 2015-02-08
        """
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
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/categories/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert ItemCategory.objects.as_of(t1).filter(identity=c.identity).exists()
        assert not ItemCategory.objects.current.filter(identity=c.identity).exists()


class PropertiesTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/properties/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_css_selector("#id_name_0").send_keys('Size')
        self.driver.find_element_by_name("values-0-value_0").send_keys('S')
        self.driver.find_element_by_name("values-1-value_0").send_keys('M')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Size", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.driver.find_element_by_partial_link_text("Size").click()
        self.assertEqual("S", self.driver.find_element_by_name("values-0-value_0").get_attribute("value"))
        self.assertEqual("M", self.driver.find_element_by_name("values-1-value_0").get_attribute("value"))

    @unittest.skipIf('TRAVIS' in os.environ, 'See CategoriesTest.test_sort for details.')
    def test_update(self):
        c = Property.objects.create(event=self.event1, name="Size")
        p1 = PropertyValue.objects.create(prop=c, position=0, value="S")
        p2 = PropertyValue.objects.create(prop=c, position=1, value="M")
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/properties/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_css_selector("#id_name_0").clear()
        self.driver.find_element_by_css_selector("#id_name_0").send_keys('Color')
        self.driver.find_elements_by_css_selector("div.form-group button.btn-danger")[0].click()
        self.scroll_into_view(self.driver.find_element_by_name("values-1-value_0"))
        self.driver.find_element_by_name("values-1-value_0").clear()
        self.driver.find_element_by_name("values-1-value_0").send_keys('red')
        self.driver.find_element_by_css_selector("button[data-formset-add]").click()
        self.driver.find_element_by_name("values-2-value_0").send_keys('blue')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertEqual("red", self.driver.find_element_by_name("values-0-value_0").get_attribute("value"))
        self.assertEqual("blue", self.driver.find_element_by_name("values-1-value_0").get_attribute("value"))
        assert str(Property.objects.current.get(identity=c.identity).name) == 'Color'
        assert str(PropertyValue.objects.as_of(t1).get(identity=p2.identity).value) == 'M'
        assert str(PropertyValue.objects.current.get(identity=p2.identity).value) == 'red'
        assert str(PropertyValue.objects.as_of(t1).get(identity=p1.identity).value) == 'S'
        assert not PropertyValue.objects.current.filter(identity=p1.identity).exists()
        assert str(Property.objects.as_of(t1).get(identity=c.identity).name) == 'Size'

    def test_delete(self):
        c = Property.objects.create(event=self.event1, name="Size")
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/properties/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Size", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert Property.objects.as_of(t1).filter(identity=c.identity).exists()
        assert not Property.objects.current.filter(identity=c.identity).exists()


class QuestionsTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/questions/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("question_0").send_keys('What is your shoe size?')
        Select(self.driver.find_element_by_name("type")).select_by_value('N')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("shoe size", self.driver.find_element_by_css_selector("#page-wrapper table").text)

    def test_update(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/questions/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("question_0").clear()
        self.driver.find_element_by_name("question_0").send_keys('How old are you?')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("How old", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        c = Question.objects.current.get(identity=c.identity)
        self.assertTrue(c.required)
        assert str(Question.objects.current.get(identity=c.identity).question) == 'How old are you?'
        assert str(Question.objects.as_of(t1).get(identity=c.identity).question) == 'What is your shoe size?'

    def test_delete(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/questions/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert Question.objects.as_of(t1).filter(identity=c.identity).exists()
        assert not Question.objects.current.filter(identity=c.identity).exists()


class QuotaTest(ItemFormTest):

    def test_create(self):
        self.driver.get('%s/control/event/%s/%s/quotas/add' % (
            self.live_server_url, self.orga1.slug, self.event1.slug
        ))
        self.driver.find_element_by_name("name").send_keys('Full house')
        self.driver.find_element_by_name("size").send_keys('500')
        self.driver.find_element_by_class_name("btn-save").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("Full house", self.driver.find_element_by_css_selector("#page-wrapper table").text)

    def test_update(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        item1 = Item.objects.create(event=self.event1, name="Standard")
        item2 = Item.objects.create(event=self.event1, name="Business")
        prop1 = Property.objects.create(event=self.event1, name="Level")
        item2.properties.add(prop1)
        PropertyValue.objects.create(prop=prop1, value="Silver")
        PropertyValue.objects.create(prop=prop1, value="Gold")
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/quotas/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_name("size").clear()
        self.driver.find_element_by_name("size").send_keys('350')
        # self.scroll_and_click(self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(1)
        # .panel-title a'))
        # time.sleep(1)
        self.scroll_and_click(self.driver.find_element_by_name("item_%s" % item1.identity))
        # self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(2) .panel-title a').click()
        # time.sleep(1)
        self.scroll_and_click(self.driver.find_elements_by_css_selector("input[name=item_%s]" % item2.identity)[1])
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("350", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("500", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert Quota.objects.current.get(identity=c.identity).size == 350
        assert Quota.objects.as_of(t1).get(identity=c.identity).size == 500
        assert item1 in Quota.objects.current.get(identity=c.identity).items.all()
        assert item1 not in Quota.objects.as_of(t1).get(identity=c.identity).items.all()

    def test_delete(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        t1 = now()
        self.driver.get('%s/control/event/%s/%s/quotas/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.identity
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Full house", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert Quota.objects.as_of(t1).filter(identity=c.identity).exists()
        assert not Quota.objects.current.filter(identity=c.identity).exists()
