import time
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator, default_token_generator,
)
from django.core import mail as djmail
from django.test import TestCase
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from u2flib_server.jsapi import JSONDict

from pretix.base.models import U2FDevice, User


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

    def test_redirect_to_2fa(self):
        self.user.require_2fa = True
        self.user.save()
        response = self.client.post('/control/login?next=/control/events/', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login/2fa?next=/control/events/', response['Location'])
        assert self.client.session['pretix_auth_2fa_user'] == self.user.pk
        assert 'pretix_auth_2fa_time' in self.client.session

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


@pytest.fixture
def class_monkeypatch(request, monkeypatch):
    request.cls.monkeypatch = monkeypatch


@pytest.mark.usefixtures("class_monkeypatch")
class Login2FAFormTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy', require_2fa=True)
        session = self.client.session
        session['pretix_auth_2fa_user'] = self.user.pk
        session['pretix_auth_2fa_time'] = str(int(time.time()))
        session.save()

    def test_invalid_session(self):
        session = self.client.session
        session['pretix_auth_2fa_user'] = self.user.pk + 12
        session['pretix_auth_2fa_time'] = str(int(time.time()))
        session.save()
        response = self.client.get('/control/login/2fa')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login', response['Location'])

    def test_expired_session(self):
        session = self.client.session
        session['pretix_auth_2fa_user'] = self.user.pk + 12
        session['pretix_auth_2fa_time'] = str(int(time.time()) - 3600)
        session.save()
        response = self.client.get('/control/login/2fa')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login', response['Location'])

    def test_totp_invalid(self):
        response = self.client.get('/control/login/2fa')
        assert 'token' in response.rendered_content
        d = TOTPDevice.objects.create(user=self.user, name='test')
        totp = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
        totp.time = time.time()
        response = self.client.post('/control/login/2fa'.format(d.pk), {
            'token': str(totp.token() + 2)
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login/2fa', response['Location'])

    def test_totp_valid(self):
        response = self.client.get('/control/login/2fa')
        assert 'token' in response.rendered_content
        d = TOTPDevice.objects.create(user=self.user, name='test')
        totp = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
        totp.time = time.time()
        response = self.client.post('/control/login/2fa?next=/control/events/'.format(d.pk), {
            'token': str(totp.token())
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/events/', response['Location'])

    def test_u2f_invalid(self):
        def fail(*args, **kwargs):
            raise Exception("Failed")

        m = self.monkeypatch
        m.setattr("u2flib_server.u2f.verify_authenticate", fail)
        m.setattr("u2flib_server.u2f.start_authenticate",
                  lambda *args, **kwargs: JSONDict({'authenticateRequests': []}))
        d = U2FDevice.objects.create(user=self.user, name='test', json_data="{}")

        response = self.client.get('/control/login/2fa')
        assert 'token' in response.rendered_content
        response = self.client.post('/control/login/2fa'.format(d.pk), {
            'token': '{"response": "true"}'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login/2fa', response['Location'])

        m.undo()

    def test_u2f_valid(self):
        m = self.monkeypatch
        m.setattr("u2flib_server.u2f.verify_authenticate", lambda *args, **kwargs: True)
        m.setattr("u2flib_server.u2f.start_authenticate",
                  lambda *args, **kwargs: JSONDict({'authenticateRequests': []}))
        d = U2FDevice.objects.create(user=self.user, name='test', json_data="{}")

        response = self.client.get('/control/login/2fa')
        assert 'token' in response.rendered_content
        response = self.client.post('/control/login/2fa'.format(d.pk), {
            'token': '{"response": "true"}'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/', response['Location'])

        m.undo()


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
