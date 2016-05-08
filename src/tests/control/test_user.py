from tests.base import BrowserTest

from pretix.base.models import User


class UserSettingsTest(BrowserTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('dummy')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("navbar-right")
        self.driver.get('%s%s' % (self.live_server_url, '/control/settings'))

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

    def test_change_email_no_duplicates(self):
        User.objects.create_user('foo@example.com', 'foo')
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
        self.driver.find_element_by_name("new_pw").send_keys("foobarbar")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("foobarbar")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.check_password("foobarbar")

    def test_change_password_short(self):
        self.driver.find_element_by_name("new_pw").send_keys("foobar")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("foobar")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_user_attribute_similarity(self):
        self.driver.find_element_by_name("new_pw").send_keys("dummy123")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("dummy123")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_require_repeat(self):
        self.driver.find_element_by_name("new_pw").send_keys("foo")
        self.driver.find_element_by_name("new_pw_repeat").send_keys("bar")
        self.driver.find_element_by_name("old_pw").send_keys("dummy")
        self.scroll_and_click(self.driver.find_element_by_class_name('btn-save'))
        self.driver.find_element_by_class_name("alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw
