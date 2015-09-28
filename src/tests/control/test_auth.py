from django.test import Client, TestCase
from tests.base import BrowserTest

from pretix.base.models import User


class LoginFormBrowserTest(BrowserTest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')

    def test_login(self):
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('dummy')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("navbar-right")

    def test_login_fail(self):
        self.driver.implicitly_wait(10)
        self.driver.get('%s%s' % (self.live_server_url, '/control/login'))
        username_input = self.driver.find_element_by_name("email")
        username_input.send_keys('dummy@dummy.dummy')
        password_input = self.driver.find_element_by_name("password")
        password_input.send_keys('wrong')
        self.driver.find_element_by_css_selector('button[type="submit"]').click()
        self.driver.find_element_by_class_name("alert-danger")


class LoginFormTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')

    def test_wrong_credentials(self):
        response = self.client.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
        })
        self.assertEqual(response.status_code, 200)

    def test_correct_credentials(self):
        response = self.client.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

    def test_inactive_account(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 200)

    def test_redirect(self):
        response = self.client.post('/control/login?next=/control/events/', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/events/', response['Location'])

    def test_logged_in(self):
        response = self.client.post('/control/login?next=/control/events/', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/events/', response['Location'])

        response = self.client.get('/control/login')
        self.assertEqual(response.status_code, 302)

        response = self.client.get('/control/login?next=/control/events/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/events/', response['Location'])

    def test_logout(self):
        response = self.client.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

        response = self.client.get('/control/logout')
        self.assertEqual(response.status_code, 302)

        response = self.client.get('/control/login')
        self.assertEqual(response.status_code, 200)


class RegistrationFormTest(TestCase):

    def test_different_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foobar'
        })
        self.assertEqual(response.status_code, 200)

    def test_email_duplicate(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foo'
        })
        self.assertEqual(response.status_code, 200)

    def test_success(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foo'
        })
        self.assertEqual(response.status_code, 302)
