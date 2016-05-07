import datetime
import os
import time
import unittest

from selenium.webdriver.support.select import Select
from tests.base import BrowserTest

from pretix.base.models import (
    Event, EventPermission, Item, ItemCategory, ItemVariation, Organizer,
    OrganizerPermission, Question, Quota, User,
)


class ItemFormTest(BrowserTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
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
        self.driver.get('%s/control/event/%s/%s/categories/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_name("name_0").clear()
        self.driver.find_element_by_name("name_0").send_keys('T-Shirts')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("T-Shirts", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert str(ItemCategory.objects.get(id=c.id).name) == 'T-Shirts'

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
        self.driver.get('%s/control/event/%s/%s/categories/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Entry tickets", self.driver.find_element_by_css_selector("#page-wrapper").text)
        assert not ItemCategory.objects.filter(id=c.id).exists()


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
        self.driver.get('%s/control/event/%s/%s/questions/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_name("question_0").clear()
        self.driver.find_element_by_name("question_0").send_keys('How old are you?')
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("How old", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        c = Question.objects.get(id=c.id)
        self.assertTrue(c.required)
        assert str(Question.objects.get(id=c.id).question) == 'How old are you?'

    def test_delete(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        self.driver.get('%s/control/event/%s/%s/questions/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("shoe size", self.driver.find_element_by_css_selector("#page-wrapper").text)
        assert not Question.objects.filter(id=c.id).exists()


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
        item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0)
        item2 = Item.objects.create(event=self.event1, name="Business", default_price=0)
        ItemVariation.objects.create(item=item2, value="Silver")
        ItemVariation.objects.create(item=item2, value="Gold")
        self.driver.get('%s/control/event/%s/%s/quotas/%s/' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_name("size").clear()
        self.driver.find_element_by_name("size").send_keys('350')
        # self.scroll_and_click(self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(1)
        # .panel-title a'))
        # time.sleep(1)
        self.scroll_and_click(self.driver.find_element_by_name("item_%s" % item1.id))
        # self.driver.find_element_by_css_selector('.panel-group .panel:nth-child(2) .panel-title a').click()
        # time.sleep(1)
        self.scroll_and_click(self.driver.find_elements_by_css_selector("input[name=item_%s]" % item2.id)[1])
        self.scroll_and_click(self.driver.find_element_by_class_name("btn-save"))
        self.driver.find_element_by_class_name("alert-success")
        self.assertIn("350", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        self.assertNotIn("500", self.driver.find_element_by_css_selector("#page-wrapper table").text)
        assert Quota.objects.get(id=c.id).size == 350
        assert item1 in Quota.objects.get(id=c.id).items.all()

    def test_delete(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        self.driver.get('%s/control/event/%s/%s/quotas/%s/delete' % (
            self.live_server_url, self.orga1.slug, self.event1.slug, c.id
        ))
        self.driver.find_element_by_class_name("btn-danger").click()
        self.driver.find_element_by_class_name("alert-success")
        self.assertNotIn("Full house", self.driver.find_element_by_css_selector("#page-wrapper").text)
        assert not Quota.objects.filter(id=c.id).exists()
