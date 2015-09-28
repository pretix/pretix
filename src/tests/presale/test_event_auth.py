from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator, default_token_generator,
)
from django.core import mail as djmail
from django.test import TestCase
from tests.presale.test_event import EventTestMixin

from pretix.base.models import User


class LoginTest(EventTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_login_invalid(self):
        response = self.client.post(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
            {
                'form': 'login',
                'email': 'demo@demo.foo',
                'password': 'bar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('alert-danger', response.rendered_content)

    def test_login_valid(self):
        response = self.client.post(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
            {
                'form': 'login',
                'email': 'demo@demo.dummy',
                'password': 'demo'
            }
        )
        self.assertEqual(response.status_code, 302)

    def test_login_already_logged_in(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        response = self.client.get(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 302)

    def test_logout(self):
        self.assertTrue(self.client.login(email='demo@demo.dummy', password='demo'))
        response = self.client.get(
            '/%s/%s/logout' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(
            '/%s/%s/login' % (self.orga.slug, self.event.slug),
        )
        self.assertEqual(response.status_code, 200)


class RegistrationFormTest(EventTestMixin, TestCase):
    def test_different_passwords(self):
        response = self.client.post('/%s/%s/login' % (self.orga.slug, self.event.slug), {
            'form': 'registration',
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foobar'
        })
        self.assertEqual(response.status_code, 200)

    def test_email_duplicate(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        response = self.client.post('/%s/%s/login' % (self.orga.slug, self.event.slug), {
            'form': 'registration',
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foo'
        })
        self.assertEqual(response.status_code, 200)

    def test_success(self):
        response = self.client.post('/%s/%s/login' % (self.orga.slug, self.event.slug), {
            'form': 'registration',
            'email': 'dummy@dummy.dummy',
            'password': 'foo',
            'password_repeat': 'foo'
        })
        self.assertEqual(response.status_code, 302)


class PasswordRecoveryFormTest(EventTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_unknown(self):
        response = self.client.post('/%s/%s/forgot' % (self.orga.slug, self.event.slug), {
            'email': 'dummy@dummy.dummy',
        })
        self.assertEqual(response.status_code, 200)

    def test_email_sent(self):
        djmail.outbox = []

        response = self.client.post('/%s/%s/forgot' % (self.orga.slug, self.event.slug), {
            'email': 'demo@demo.dummy',
        })
        self.assertEqual(response.status_code, 302)

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [self.user.email]
        assert "recover?id=%d&token=" % self.user.id in djmail.outbox[0].body

    def test_recovery_unknown_user(self):
        response = self.client.get('/%s/%s/forgot/recover?id=0&token=foo' % (self.orga.slug, self.event.slug))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=0&token=foo' % (self.orga.slug, self.event.slug),
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_invalid_token(self):
        response = self.client.get(
            '/%s/%s/forgot/recover?id=%d&token=foo' % (self.orga.slug, self.event.slug, self.user.id)
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=%d&token=foo' % (self.orga.slug, self.event.slug, self.user.id),
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
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
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token)
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token),
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_success(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token)
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token),
            {
                'password': 'foobar',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 302)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('foobar'))

    def test_recovery_valid_token_empty_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token)
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token),
            {
                'password': '',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))

    def test_recovery_valid_token_different_passwords(self):
        token = default_token_generator.make_token(self.user)
        response = self.client.get(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token)
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/%s/%s/forgot/recover?id=%d&token=%s' % (self.orga.slug, self.event.slug, self.user.id, token),
            {
                'password': 'foo',
                'password_repeat': 'foobar'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.user = User.objects.get(id=self.user.id)
        self.assertTrue(self.user.check_password('demo'))
