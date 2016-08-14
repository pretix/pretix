from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator, default_token_generator,
)
from django.core import mail as djmail
from django.test import TestCase

from pretix.base.models import User


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

    def test_user_attribute_similarity_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummydummy',
            'password_repeat': 'dummydummy'
        })
        self.assertEqual(response.status_code, 200)

    def test_short_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foobar',
            'password_repeat': 'foobar'
        })
        self.assertEqual(response.status_code, 200)

    def test_common_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'password',
            'password_repeat': 'password'
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'football',
            'password_repeat': 'football'
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'jennifer',
            'password_repeat': 'jennifer'
        })
        self.assertEqual(response.status_code, 200)

    def test_numeric_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': '12345678',
            'password_repeat': '12345678'
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': '23423523452345235',
            'password_repeat': '23423523452345235'
        })
        self.assertEqual(response.status_code, 200)

    def test_empty_passwords(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': '',
            'password_repeat': ''
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foobarbar',
            'password_repeat': ''
        })
        self.assertEqual(response.status_code, 200)

    def test_email_duplicate(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foobarbar',
            'password_repeat': 'foobarbar'
        })
        self.assertEqual(response.status_code, 200)

    def test_success(self):
        response = self.client.post('/control/register', {
            'email': 'dummy@dummy.dummy',
            'password': 'foobarbar',
            'password_repeat': 'foobarbar'
        })
        self.assertEqual(response.status_code, 302)


class PasswordRecoveryFormTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_unknown(self):
        response = self.client.post('/control/forgot', {
            'email': 'dummy@dummy.dummy',
            })
        self.assertEqual(response.status_code, 200)

    def test_email_sent(self):
        djmail.outbox = []

        response = self.client.post('/control/forgot', {
            'email': 'demo@demo.dummy',
            })
        self.assertEqual(response.status_code, 302)

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [self.user.email]
        assert "recover?id=%d&token=" % self.user.id in djmail.outbox[0].body

    def test_recovery_unknown_user(self):
        response = self.client.get('/control/forgot/recover?id=0&token=foo')
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/control/forgot/recover?id=0&token=foo',
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_invalid_token(self):
        response = self.client.get('/control/forgot/recover?id=%d&token=foo' % self.user.id)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=foo' % self.user.id,
            {
                'password': 'foobarbar',
                'password_repeat': 'foobarbar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_expired_token(self):
        class Mocked(PasswordResetTokenGenerator):
            def _today(self):
                return date.today() - timedelta(settings.PASSWORD_RESET_TIMEOUT_DAYS + 1)

        generator = Mocked()
        token = generator.make_token(self.user)
        response = self.client.get(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token)
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'foobarbar',
                'password_repeat': 'foobarbar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_success(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'foobarbar',
                'password_repeat': 'foobarbar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('foobarbar'))

    def test_recovery_valid_token_empty_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'foobarbar',
                'password_repeat': ''
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': '',
                'password_repeat': 'foobarbar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_different_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'foo',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_user_attribute_similarity_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'dummydemo',
                'password_repeat': 'dummydemo'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_short_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_common_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': 'football',
                'password_repeat': 'football'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_numeric_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get('/control/forgot/recover?id=%d&token=%s' % (self.user.id, token))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/control/forgot/recover?id=%d&token=%s' % (self.user.id, token),
            {
                'password': '12345678',
                'password_repeat': '12345678'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))
