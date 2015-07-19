import time

from tests.base import BrowserTest
from tests.presale.test_event import EventTestMixin

from pretix.base.models import User


class UserSettingsTest(EventTestMixin, BrowserTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_global_user('dummy@dummy.dummy', 'dummy')
        self.driver.implicitly_wait(10)
        self.driver.get('%s/%s/%s/login' % (self.live_server_url, self.orga.slug, self.event.slug))
        # open the login accordion
        self.scroll_and_click(self.driver.find_element_by_css_selector('a[href*=loginForm]'))
        time.sleep(1)
        # enter login details
        self.driver.find_element_by_css_selector('#loginForm input[name=username]').send_keys('dummy@dummy.dummy')
        self.driver.find_element_by_css_selector('#loginForm input[name=password]').send_keys('dummy')
        self.scroll_and_click(self.driver.find_element_by_css_selector('#loginForm button.btn-primary'))
        self.driver.find_element_by_partial_link_text('Your account')
        self.driver.get('%s/%s/%s/account/settings' % (self.live_server_url, self.orga.slug, self.event.slug))

    def test_set_name(self):
        self.driver.find_element_by_name("givenname").clear()
        self.driver.find_element_by_name("familyname").clear()
        self.driver.find_element_by_name("givenname").send_keys("Peter")
        self.driver.find_element_by_name("familyname").send_keys("Miller")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.givenname == 'Peter'
        assert self.user.familyname == 'Miller'

    def test_change_email_require_password(self):
        self.driver.find_element_by_name("email").clear()
        self.driver.find_element_by_name("email").send_keys("foo@example.com")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_email_success(self):
        self.driver.find_element_by_name("email").clear()
        self.driver.find_element_by_name("email").send_keys("foo@example.com")
        self.driver.find_element_by_name("old_pw").clear()
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'foo@example.com'

    def test_change_email_allow_local_duplicates(self):
        User.objects.create_local_user(event=self.event, username='test', email='foo@example.com', password='foo')
        self.driver.find_element_by_name("email").clear()
        self.driver.find_element_by_name("email").send_keys("foo@example.com")
        self.driver.find_element_by_name("old_pw").clear()
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'foo@example.com'

    def test_change_email_no_global_duplicates(self):
        User.objects.create_global_user('foo@example.com', 'foo')
        self.driver.find_element_by_name("email").clear()
        self.driver.find_element_by_name("email").send_keys("foo@example.com")
        self.driver.find_element_by_name("old_pw").clear()
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_password_require_password(self):
        self.driver.find_element_by_name("new_pw").send_keys("foo")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("foo")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_success(self):
        self.driver.find_element_by_name("new_pw").send_keys("foo")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("foo")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.check_password("foo")

    def test_change_password_require_repeat(self):
        self.driver.find_element_by_name("new_pw").send_keys("foo")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("bar")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw
