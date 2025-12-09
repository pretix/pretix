#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import re
import time

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from tests.base import SoupTest, extract_form_fields
from webauthn.registration.verify_registration_response import (
    VerifiedRegistration,
)

from pretix.base.models import (
    Event, Organizer, U2FDevice, User, WebAuthnDevice,
)
from pretix.testutils.mock import mocker_context


class UserSettingsTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        self.client.login(email='dummy@dummy.dummy', password='old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        doc = self.get_doc('/control/settings')
        self.form_data = extract_form_fields(doc.select('form[data-testid="usersettingsform"]')[0])

    def save(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        return self.post_doc('/control/settings', form_data)

    def test_set_name(self):
        doc = self.save({
            'fullname': 'Peter Miller',
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.fullname == 'Peter Miller'

    def test_set_locale_and_timezone(self):
        doc = self.save({
            'locale': 'fr',
            'timezone': 'Europe/Paris',
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.locale == 'fr'
        assert self.user.timezone == 'Europe/Paris'


class UserEmailChangeTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        self.client.login(email='dummy@dummy.dummy', password='old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time())
        session.save()
        doc = self.get_doc('/control/settings/email/change')
        self.form_data = extract_form_fields(doc.select('.container-fluid form')[0])

    def test_require_reauth(self):
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 2
        session.save()

        response = self.client.get('/control/settings/email/change')
        self.assertIn('/control/reauth', response['Location'])
        self.assertEqual(response.status_code, 302)

        response = self.client.post('/control/reauth/?next=/control/settings/email/change', {
            'password': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9'
        })
        self.assertIn('/control/settings/email/change', response['Location'])
        self.assertEqual(response.status_code, 302)

    def submit_step_1(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        return self.post_doc('/control/settings/email/change', form_data)

    def submit_step_2(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        return self.post_doc('/control/settings/email/confirm?reason=email_change', form_data)

    def test_change_email_success(self):
        djmail.outbox = []
        doc = self.submit_step_1({
            'new_email': 'foo@example.com',
        })
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['foo@example.com']
        code = re.search("[0-9]{7}", djmail.outbox[0].body).group(0)
        doc = self.submit_step_2({
            'code': code,
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'foo@example.com'

    def test_change_email_wrong_code(self):
        djmail.outbox = []
        doc = self.submit_step_1({
            'new_email': 'foo@example.com',
        })
        assert len(djmail.outbox) == 1
        assert djmail.outbox[0].to == ['foo@example.com']
        code = re.search("[0-9]{7}", djmail.outbox[0].body).group(0)
        wrong_code = '0000000' if code == '1234567' else '1234567'
        doc = self.submit_step_2({
            'code': wrong_code,
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_email_no_duplicates(self):
        User.objects.create_user('foo@example.com', 'foo')
        doc = self.submit_step_1({
            'new_email': 'foo@example.com',
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'


class UserPasswordChangeTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        self.client.login(email='dummy@dummy.dummy', password='old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9')
        doc = self.get_doc('/control/settings/password/change')
        self.form_data = extract_form_fields(doc.select('.container-fluid form')[0])

    def save(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        return self.post_doc('/control/settings/password/change', form_data)

    def test_change_password_require_password(self):
        doc = self.save({
            'new_pw': 'f00barbarbar',
            'new_pw_repeat': 'f00barbarbar',
        })
        assert doc.select(".alert-danger")
        assert "This field is required." in doc.select(".has-error")[0].text
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_old_password_wrong(self):
        doc = self.save({
            'new_pw': 'f00barbarbar',
            'new_pw_repeat': 'f00barbarbar',
            'old_pw': 'lolwrong',
        })
        assert doc.select(".alert-danger")
        assert "The current password you entered was not correct." in doc.select(".has-error")[0].text
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_wrong_backend(self):
        self.user.auth_backend = 'test_request'
        self.user.save()
        self.save({
            'new_pw': 'f00barbarbar',
            'new_pw_repeat': 'f00barbarbar',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_success(self):
        doc = self.save({
            'new_pw': 'f00barbarbar',
            'new_pw_repeat': 'f00barbarbar',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.check_password("f00barbarbar")

    def test_change_password_short(self):
        doc = self.save({
            'new_pw': 'foo',
            'new_pw_repeat': 'foo',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-danger")
        assert "This password is too short." in doc.select(".has-error")[0].text
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_user_attribute_similarity(self):
        doc = self.save({
            'new_pw': 'dummy123',
            'new_pw_repeat': 'dummy123',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-danger")
        assert "The password is too similar to the Email." in doc.select(".has-error")[0].text
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_require_repeat(self):
        doc = self.save({
            'new_pw': 'foooooooooooooo1234',
            'new_pw_repeat': 'baaaaaaaaaaaar1234',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-danger")
        assert "Please enter the same password twice" in doc.select(".has-error")[0].text
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_require_new(self):
        doc = self.save({
            'new_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'new_pw_repeat': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".has-error")
        assert "Your password may not be the same as" in doc.select(".has-error")[0].text

    def test_change_password_history(self):
        doc = self.save({
            'new_pw': 'qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'new_pw_repeat': 'qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-success")

        doc = self.save({
            'new_pw': '9UQl4lSwHLMVUIMgw0L1X8XEFmyvdn',
            'new_pw_repeat': '9UQl4lSwHLMVUIMgw0L1X8XEFmyvdn',
            'old_pw': 'qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
        })
        assert doc.select(".alert-success")

        doc = self.save({
            'new_pw': 'qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'new_pw_repeat': 'qvuSpukdKWUV7m7PoRrWwpCd2Taij9',
            'old_pw': '9UQl4lSwHLMVUIMgw0L1X8XEFmyvdn',
        })
        assert doc.select(".alert-danger")
        assert "Your password may not be the same as one of your 4 previous passwords." in doc.select(".has-error")[0].text

    def test_needs_password_change_changed(self):
        self.user.needs_password_change = True
        self.user.save()
        self.save({
            'new_pw': 'f00barbarbar',
            'new_pw_repeat': 'f00barbarbar',
            'old_pw': 'old_qvuSpukdKWUV7m7PoRrWwpCd2Taij9'
        })
        self.user.refresh_from_db()
        assert self.user.needs_password_change is False


@pytest.fixture
def class_monkeypatch(request, monkeypatch):
    request.cls.monkeypatch = monkeypatch


@pytest.mark.usefixtures("class_monkeypatch")
class UserSettings2FATest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.client.login(email='dummy@dummy.dummy', password='dummy')
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time())
        session.save()

    def test_require_reauth(self):
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time()) - 3600 * 2
        session.save()

        response = self.client.get('/control/settings/2fa/')
        self.assertIn('/control/reauth', response['Location'])
        self.assertEqual(response.status_code, 302)

        response = self.client.post('/control/reauth/?next=/control/settings/2fa/', {
            'password': 'dummy'
        })
        self.assertIn('/control/settings/2fa/', response['Location'])
        self.assertEqual(response.status_code, 302)

    def test_enable_require_device(self):
        r = self.client.post('/control/settings/2fa/enable', follow=True)
        assert 'alert-danger' in r.content.decode()
        self.user.refresh_from_db()
        assert not self.user.require_2fa

    def test_enable(self):
        U2FDevice.objects.create(user=self.user, name='Test')
        r = self.client.post('/control/settings/2fa/enable', follow=True)
        assert 'alert-success' in r.content.decode()
        self.user.refresh_from_db()
        assert self.user.require_2fa

    def test_disable(self):
        self.user.require_2fa = True
        self.user.save()
        r = self.client.post('/control/settings/2fa/disable', follow=True)
        assert 'alert-success' in r.content.decode()
        self.user.refresh_from_db()
        assert not self.user.require_2fa

    def test_gen_emergency(self):
        self.client.get('/control/settings/2fa/')
        d = StaticDevice.objects.get(user=self.user, name='emergency')
        assert d.token_set.count() == 10
        old_tokens = set(t.token for t in d.token_set.all())
        self.client.post('/control/settings/2fa/regenemergency')
        new_tokens = set(t.token for t in d.token_set.all())
        d = StaticDevice.objects.get(user=self.user, name='emergency')
        assert d.token_set.count() == 10
        assert old_tokens != new_tokens

    def test_delete_u2f(self):
        d = U2FDevice.objects.create(user=self.user, name='Test')
        self.client.get('/control/settings/2fa/u2f/{}/delete'.format(d.pk))
        self.client.post('/control/settings/2fa/u2f/{}/delete'.format(d.pk))
        assert not U2FDevice.objects.exists()

    def test_delete_webauthn(self):
        d = WebAuthnDevice.objects.create(user=self.user, name='Test')
        self.client.get('/control/settings/2fa/webauthn/{}/delete'.format(d.pk))
        self.client.post('/control/settings/2fa/webauthn/{}/delete'.format(d.pk))
        assert not WebAuthnDevice.objects.exists()

    def test_delete_totp(self):
        d = TOTPDevice.objects.create(user=self.user, name='Test')
        self.client.get('/control/settings/2fa/totp/{}/delete'.format(d.pk))
        self.client.post('/control/settings/2fa/totp/{}/delete'.format(d.pk))
        assert not TOTPDevice.objects.exists()

    def test_create_webauthn_require_https(self):
        r = self.client.post('/control/settings/2fa/add', {
            'devicetype': 'webauthn',
            'name': 'Foo'
        })
        assert 'alert-danger' in r.content.decode()

    def test_create_webauthn(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'webauthn',
                'name': 'Foo'
            })
            d = WebAuthnDevice.objects.first()
            assert d.name == 'Foo'
            assert not d.confirmed

    def test_create_totp(self):
        self.client.post('/control/settings/2fa/add', {
            'devicetype': 'totp',
            'name': 'Foo'
        })
        d = TOTPDevice.objects.first()
        assert d.name == 'Foo'

    def test_confirm_totp(self):
        self.client.post('/control/settings/2fa/add', {
            'devicetype': 'totp',
            'name': 'Foo'
        }, follow=True)
        d = TOTPDevice.objects.first()
        totp = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
        totp.time = time.time()
        r = self.client.post('/control/settings/2fa/totp/{}/confirm'.format(d.pk), {
            'token': str(totp.token()),
            'activate': 'on'
        }, follow=True)
        d.refresh_from_db()
        assert d.confirmed
        assert 'alert-success' in r.content.decode()
        self.user.refresh_from_db()
        assert self.user.require_2fa

    def test_confirm_totp_failed(self):
        self.client.post('/control/settings/2fa/add', {
            'devicetype': 'totp',
            'name': 'Foo'
        }, follow=True)
        d = TOTPDevice.objects.first()
        totp = TOTP(d.bin_key, d.step, d.t0, d.digits, d.drift)
        totp.time = time.time()
        r = self.client.post('/control/settings/2fa/totp/{}/confirm'.format(d.pk), {
            'token': str(totp.token() - 2)
        }, follow=True)
        assert 'alert-danger' in r.content.decode()
        d.refresh_from_db()
        assert not d.confirmed

    def test_confirm_webauthn_failed(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'webauthn',
                'name': 'Foo'
            }, follow=True)
        d = WebAuthnDevice.objects.first()
        r = self.client.post('/control/settings/2fa/webauthn/{}/confirm'.format(d.pk), {
            'token': 'FOO'
        }, follow=True)
        assert 'alert-danger' in r.content.decode()
        d.refresh_from_db()
        assert not d.confirmed

    def test_confirm_webauthn_success(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'webauthn',
                'name': 'Foo'
            }, follow=True)

        m = self.monkeypatch
        m.setattr("webauthn.verify_registration_response",
                  lambda *args, **kwargs: VerifiedRegistration(
                      b'', b'', 1, '', 'foo', 'public-key', True, b'', 'single_device', True
                  ))

        d = WebAuthnDevice.objects.first()
        r = self.client.post('/control/settings/2fa/webauthn/{}/confirm'.format(d.pk), {
            'token': '{}',
            'activate': 'on'
        }, follow=True)
        d.refresh_from_db()
        assert d.confirmed
        assert 'alert-success' in r.content.decode()
        self.user.refresh_from_db()
        assert self.user.require_2fa
        m.undo()


class UserSettingsNotificationsTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.client.login(email='dummy@dummy.dummy', password='dummy')

        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), plugins='pretix.plugins.banktransfer'
        )
        t = o.teams.create(can_change_orders=True, all_events=True)
        t.members.add(self.user)

    def test_toggle_all(self):
        assert self.user.notifications_send
        self.client.post('/control/settings/notifications/', {
            'notifications_send': 'off'
        })
        self.user.refresh_from_db()
        assert not self.user.notifications_send
        self.client.post('/control/settings/notifications/', {
            'notifications_send': 'on'
        })
        self.user.refresh_from_db()
        assert self.user.notifications_send

    def test_global_enable(self):
        self.client.post('/control/settings/notifications/', {
            'mail:pretix.event.order.placed': 'on'
        })
        assert self.user.notification_settings.get(
            event__isnull=True, method='mail', action_type='pretix.event.order.placed'
        ).enabled is True

    def test_global_disable(self):
        self.user.notification_settings.create(
            event=None, method='mail', action_type='pretix.event.order.placed', enabled=True
        )
        self.client.post('/control/settings/notifications/', {
            'mail:pretix.event.order.placed': 'off'
        })
        assert self.user.notification_settings.get(
            event__isnull=True, method='mail', action_type='pretix.event.order.placed'
        ).enabled is False

    def test_event_enabled_disable(self):
        self.user.notification_settings.create(
            event=self.event, method='mail', action_type='pretix.event.order.placed', enabled=True
        )
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'off'
        })
        assert self.user.notification_settings.get(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).enabled is False

    def test_event_global_disable(self):
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'off'
        })
        assert self.user.notification_settings.get(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).enabled is False

    def test_event_disabled_enable(self):
        self.user.notification_settings.create(
            event=self.event, method='mail', action_type='pretix.event.order.placed', enabled=False
        )
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'on'
        })
        assert self.user.notification_settings.get(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).enabled is True

    def test_event_global_enable(self):
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'on'
        })
        assert self.user.notification_settings.get(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).enabled is True

    def test_event_enabled_global(self):
        self.user.notification_settings.create(
            event=self.event, method='mail', action_type='pretix.event.order.placed', enabled=True
        )
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'global'
        })
        assert not self.user.notification_settings.filter(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).exists()

    def test_event_disabled_global(self):
        self.user.notification_settings.create(
            event=self.event, method='mail', action_type='pretix.event.order.placed', enabled=False
        )
        self.client.post('/control/settings/notifications/?event={}'.format(self.event.pk), {
            'mail:pretix.event.order.placed': 'global'
        })
        assert not self.user.notification_settings.filter(
            event=self.event, method='mail', action_type='pretix.event.order.placed'
        ).exists()

    def test_disable_all_via_link(self):
        assert self.user.notifications_send
        self.client.post('/control/settings/notifications/off/{}/{}/'.format(self.user.pk, self.user.notifications_token))
        self.user.refresh_from_db()
        assert not self.user.notifications_send

    def test_disable_all_via_link_anonymous(self):
        self.client.logout()
        assert self.user.notifications_send
        self.client.post('/control/settings/notifications/off/{}/{}/'.format(self.user.pk, self.user.notifications_token))
        self.user.refresh_from_db()
        assert not self.user.notifications_send
