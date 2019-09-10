import time
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator, default_token_generator,
)
from django.core import mail as djmail
from django.test import TestCase, override_settings
from django.utils.timezone import now
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

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
        assert time.time() - self.client.session['pretix_auth_login_time'] < 60
        assert not self.client.session['pretix_auth_long_session']

    def test_set_long_session(self):
        response = self.client.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
            'keep_logged_in': 'on'
        })
        self.assertEqual(response.status_code, 302)
        assert self.client.session['pretix_auth_long_session']

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
        assert time.time() - self.client.session['pretix_auth_login_time'] < 60
        assert not self.client.session['pretix_auth_long_session']


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
        session['pretix_auth_long_session'] = False
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
        assert 'token' in response.content.decode()
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
        assert 'token' in response.content.decode()
        d = TOTPDevice.objects.create(user=self.user, name='test')
        totp = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
        totp.time = time.time()
        response = self.client.post('/control/login/2fa?next=/control/events/'.format(d.pk), {
            'token': str(totp.token())
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/events/', response['Location'])
        assert time.time() - self.client.session['pretix_auth_login_time'] < 60
        assert not self.client.session['pretix_auth_long_session']

    def test_u2f_invalid(self):
        def fail(*args, **kwargs):
            raise Exception("Failed")

        m = self.monkeypatch
        m.setattr("webauthn.WebAuthnAssertionResponse.verify", fail)
        d = U2FDevice.objects.create(
            user=self.user, name='test',
            json_data='{"appId": "https://local.pretix.eu", "keyHandle": '
                      '"j9Rkpon1J5U3eDQMM8YqAvwEapt-m87V8qdCaImiAqmvTJ'
                      '-sBvnACIKKM6J_RVXF4jPtY0LGyjbHi14sxsoC5g", "publ'
                      'icKey": "BP5KRLUGvcHbqkCc7eJNXZ9caVXLSk4wjsq'
                      'L-pLEQcNqVp2E4OeDUIxI0ZLOXry9JSrLn1aAGcGowXiIyB7ynj0"}')

        response = self.client.get('/control/login/2fa')
        assert 'token' in response.content.decode()
        response = self.client.post('/control/login/2fa'.format(d.pk), {
            'token': '{"response": "true"}'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/login/2fa', response['Location'])

        m.undo()

    def test_u2f_valid(self):
        m = self.monkeypatch
        m.setattr("webauthn.WebAuthnAssertionResponse.verify", lambda *args, **kwargs: 1)

        d = U2FDevice.objects.create(
            user=self.user, name='test',
            json_data='{"appId": "https://local.pretix.eu", "keyHandle": '
                      '"j9Rkpon1J5U3eDQMM8YqAvwEapt-m87V8qdCaImiAqmvTJ'
                      '-sBvnACIKKM6J_RVXF4jPtY0LGyjbHi14sxsoC5g", "publ'
                      'icKey": "BP5KRLUGvcHbqkCc7eJNXZ9caVXLSk4wjsq'
                      'L-pLEQcNqVp2E4OeDUIxI0ZLOXry9JSrLn1aAGcGowXiIyB7ynj0"}')

        response = self.client.get('/control/login/2fa')
        assert 'token' in response.content.decode()
        response = self.client.post('/control/login/2fa'.format(d.pk), {
            'token': '{"response": "true"}'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/control/', response['Location'])

        m.undo()


class FakeRedis(object):
    def get_redis_connection(self, connection_string):
        return self

    def __init__(self):
        self.storage = {}

    def pipeline(self):
        return self

    def hincrbyfloat(self, rkey, key, amount):
        return self

    def commit(self):
        return self

    def exists(self, rkey):
        print(rkey in self.storage)
        return rkey in self.storage

    def setex(self, rkey, value, expiration):
        self.storage[rkey] = value

    def execute(self):
        pass


@pytest.mark.usefixtures("class_monkeypatch")
class PasswordRecoveryFormTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')

    def test_unknown(self):
        djmail.outbox = []

        response = self.client.post('/control/forgot', {
            'email': 'dummy@dummy.dummy',
        })
        self.assertEqual(response.status_code, 302)
        assert len(djmail.outbox) == 0

    def test_email_sent(self):
        djmail.outbox = []

        response = self.client.post('/control/forgot', {
            'email': 'demo@demo.dummy',
        })
        self.assertEqual(response.status_code, 302)

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [self.user.email]
        assert "recover?id=%d&token=" % self.user.id in djmail.outbox[0].body
        assert self.user.all_logentries[0].action_type == 'pretix.control.auth.user.forgot_password.mail_sent'

    @override_settings(HAS_REDIS=True)
    def test_email_reset_twice_redis(self):
        fake_redis = FakeRedis()
        m = self.monkeypatch
        m.setattr('django_redis.get_redis_connection', fake_redis.get_redis_connection, raising=False)
        m.setattr('pretix.base.metrics.redis', fake_redis, raising=False)

        djmail.outbox = []

        response = self.client.post('/control/forgot', {
            'email': 'demo@demo.dummy',
        })
        self.assertEqual(response.status_code, 302)

        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == [self.user.email]
        assert "recover?id=%d&token=" % self.user.id in djmail.outbox[0].body
        assert self.user.all_logentries[0].action_type == 'pretix.control.auth.user.forgot_password.mail_sent'

        response = self.client.post('/control/forgot', {
            'email': 'demo@demo.dummy',
        })
        self.assertEqual(response.status_code, 302)

        assert len(djmail.outbox) == 1
        assert self.user.all_logentries[0].action_type == 'pretix.control.auth.user.forgot_password.denied.repeated'

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


class SessionTimeOutTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')
        self.client.login(email='demo@demo.dummy', password='demo')

    def test_log_out_after_absolute_timeout(self):
        session = self.client.session
        session['pretix_auth_long_session'] = False
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)

    def test_dont_logout_before_absolute_timeout(self):
        session = self.client.session
        session['pretix_auth_long_session'] = True
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 + 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

    @override_settings(PRETIX_LONG_SESSIONS=False)
    def test_ignore_long_session_if_disabled_in_config(self):
        session = self.client.session
        session['pretix_auth_long_session'] = True
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)

    def test_dont_logout_in_long_session(self):
        session = self.client.session
        session['pretix_auth_long_session'] = True
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 12 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

    def test_log_out_after_relative_timeout(self):
        session = self.client.session
        session['pretix_auth_long_session'] = False
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
        session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)

    def test_dont_logout_before_relative_timeout(self):
        session = self.client.session
        session['pretix_auth_long_session'] = True
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
        session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 + 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

    def test_dont_logout_by_relative_in_long_session(self):
        session = self.client.session
        session['pretix_auth_long_session'] = True
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
        session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

    def test_log_out_after_relative_timeout_really_enforced(self):
        # Regression test added after a security problem in 1.9.1
        # The problem was that, once the relative timeout happened, the user was redirected
        # to /control/reauth/, but loading /control/reauth/ was already considered to be
        # "session activitiy". Therefore, after loding /control/reauth/, the session was no longer
        # in the timeout state and the user was able to access pages again without re-entering the
        # password.
        session = self.client.session
        session['pretix_auth_long_session'] = False
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 6
        session['pretix_auth_last_used'] = int(time.time()) - 3600 * 3 - 60
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/control/reauth/?next=/control/')
        self.client.get('/control/reauth/?next=/control/')
        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)

    def test_update_session_activity(self):
        t1 = int(time.time()) - 5
        session = self.client.session
        session['pretix_auth_long_session'] = False
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 5
        session['pretix_auth_last_used'] = t1
        session.save()

        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

        assert self.client.session['pretix_auth_last_used'] > t1

    def test_pinned_user_agent(self):
        self.client.defaults['HTTP_USER_AGENT'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36'
        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 200)

        self.client.defaults['HTTP_USER_AGENT'] = 'Mozilla/5.0 (X11; Linux x86_64) Something else'
        response = self.client.get('/control/')
        self.assertEqual(response.status_code, 302)


@pytest.fixture
def user():
    user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    return user


@pytest.mark.django_db
def test_impersonate(user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    user.is_staff = True
    user.save()
    ss = user.staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    t1 = int(time.time()) - 5
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = t1
    session['pretix_auth_last_used'] = t1
    session.save()
    user2 = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    response = client.post('/control/users/{user}/impersonate'.format(user=user2.pk), follow=True)
    assert b'dummy2@' in response.content
    response = client.get('/control/global/settings/')
    assert response.status_code == 403
    response = client.get('/control/')
    response = client.post('/control/users/impersonate/stop', follow=True)
    assert b'dummy@' in response.content
    assert b'dummy2@' not in response.content
    response = client.get('/control/global/settings/')
    assert response.status_code == 200  # staff session is preserved
    assert ss.logs.filter(url='/control/', impersonating=user2).exists()


@pytest.mark.django_db
def test_impersonate_require_recent_auth(user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    user.is_staff = True
    user.save()
    user.staffsession_set.create(date_start=now(), session_key=client.session.session_key)
    t1 = int(time.time()) - 5 * 3600
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = t1
    session['pretix_auth_last_used'] = t1
    session.save()
    user2 = User.objects.create_user('dummy2@dummy.dummy', 'dummy')
    response = client.post('/control/users/{user}/impersonate'.format(user=user2.pk), follow=True)
    assert b'dummy2@' not in response.content


@pytest.mark.django_db
def test_staff_session(user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    user.is_staff = True
    user.save()
    t1 = int(time.time()) - 5
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = t1
    session['pretix_auth_last_used'] = t1
    session.save()
    response = client.get('/control/global/settings/')
    assert response.status_code == 302
    response = client.post('/control/sudo/')
    assert response['Location'] == '/control/'
    response = client.get('/control/global/settings/')
    assert response.status_code == 200
    client.post('/control/sudo/stop', follow=True)
    response = client.get('/control/global/settings/')
    assert response.status_code == 302
    assert user.staffsession_set.last().logs.filter(url='/control/global/settings/').exists()


@pytest.mark.django_db
def test_staff_session_require_recent_auth(user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    user.is_staff = True
    user.save()
    t1 = int(time.time()) - 5 * 3600
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = t1
    session['pretix_auth_last_used'] = t1
    session.save()
    response = client.post('/control/sudo/')
    assert response['Location'].startswith('/control/reauth/')


@pytest.mark.django_db
def test_staff_session_require_staff(user, client):
    user.is_staff = False
    user.save()
    client.login(email='dummy@dummy.dummy', password='dummy')
    t1 = int(time.time()) - 5
    session = client.session
    session['pretix_auth_long_session'] = False
    session['pretix_auth_login_time'] = t1
    session['pretix_auth_last_used'] = t1
    session.save()
    response = client.post('/control/sudo/')
    assert response.status_code == 403


@override_settings(PRETIX_OBLIGATORY_2FA=True)
class Obligatory2FATest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('demo@demo.dummy', 'demo')
        self.client.login(email='demo@demo.dummy', password='demo')

    def test_enabled_2fa_not_setup(self):
        response = self.client.get('/control/events/')
        assert response.status_code == 302
        assert response.url == '/control/settings/2fa/'

    def test_enabled_2fa_setup_not_enabled(self):
        U2FDevice.objects.create(user=self.user, name='test', json_data="{}", confirmed=True)
        self.user.require_2fa = False
        self.user.save()

        response = self.client.get('/control/events/')
        assert response.status_code == 302
        assert response.url == '/control/settings/2fa/'

    def test_enabled_2fa_setup_enabled(self):
        U2FDevice.objects.create(user=self.user, name='test', json_data="{}", confirmed=True)
        self.user.require_2fa = True
        self.user.save()

        response = self.client.get('/control/events/')
        assert response.status_code == 200
