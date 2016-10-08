import time

from _pytest import monkeypatch
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from tests.base import SoupTest, extract_form_fields
from u2flib_server.jsapi import JSONDict

from pretix.base.models import U2FDevice, User
from pretix.testutils.mock import mocker_context


class UserSettingsTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.client.login(email='dummy@dummy.dummy', password='dummy')
        doc = self.get_doc('/control/settings')
        self.form_data = extract_form_fields(doc.select('.container-fluid form')[0])

    def save(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        return self.post_doc('/control/settings', form_data)

    def test_set_name(self):
        doc = self.save({
            'givenname': 'Peter',
            'familyname': 'Miller'
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.givenname == 'Peter'
        assert self.user.familyname == 'Miller'

    def test_change_email_require_password(self):
        doc = self.save({
            'email': 'foo@example.com',
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_email_success(self):
        doc = self.save({
            'email': 'foo@example.com',
            'old_pw': 'dummy'
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'foo@example.com'

    def test_change_email_no_duplicates(self):
        User.objects.create_user('foo@example.com', 'foo')
        doc = self.save({
            'email': 'foo@example.com',
            'old_pw': 'dummy'
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_password_require_password(self):
        doc = self.save({
            'new_pw': 'foo',
            'new_pw_repeat': 'foo',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_success(self):
        doc = self.save({
            'new_pw': 'foobarbar',
            'new_pw_repeat': 'foobarbar',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.check_password("foobarbar")

    def test_change_password_short(self):
        doc = self.save({
            'new_pw': 'foo',
            'new_pw_repeat': 'foo',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_user_attribute_similarity(self):
        doc = self.save({
            'new_pw': 'dummy123',
            'new_pw_repeat': 'dummy123',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_require_repeat(self):
        doc = self.save({
            'new_pw': 'foooooooooooooo',
            'new_pw_repeat': 'baaaaaaaaaaaar',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw


class UserSettings2FATest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_enable_require_device(self):
        r = self.client.post('/control/settings/2fa/enable', follow=True)
        assert 'alert-danger' in r.rendered_content
        self.user.refresh_from_db()
        assert not self.user.require_2fa

    def test_enable(self):
        U2FDevice.objects.create(user=self.user, name='Test')
        r = self.client.post('/control/settings/2fa/enable', follow=True)
        assert 'alert-success' in r.rendered_content
        self.user.refresh_from_db()
        assert self.user.require_2fa

    def test_disable(self):
        self.user.require_2fa = True
        self.user.save()
        r = self.client.post('/control/settings/2fa/disable', follow=True)
        assert 'alert-success' in r.rendered_content
        self.user.refresh_from_db()
        assert not self.user.require_2fa

    def test_gen_emergency(self):
        self.client.get('/control/settings/2fa/')
        d = StaticDevice.objects.get(user=self.user, name='emergency')
        assert d.token_set.count() == 10
        old_tokens = set(t.token for t in d.token_set.all())
        self.client.post('/control/settings/2fa/regenemergency')
        new_tokens = set(t.token for t in d.token_set.all())
        assert d.token_set.count() == 10
        assert old_tokens != new_tokens

    def test_delete_u2f(self):
        d = U2FDevice.objects.create(user=self.user, name='Test')
        self.client.get('/control/settings/2fa/u2f/{}/delete'.format(d.pk))
        self.client.post('/control/settings/2fa/u2f/{}/delete'.format(d.pk))
        assert not U2FDevice.objects.exists()

    def test_delete_totp(self):
        d = TOTPDevice.objects.create(user=self.user, name='Test')
        self.client.get('/control/settings/2fa/totp/{}/delete'.format(d.pk))
        self.client.post('/control/settings/2fa/totp/{}/delete'.format(d.pk))
        assert not TOTPDevice.objects.exists()

    def test_create_u2f_require_https(self):
        r = self.client.post('/control/settings/2fa/add', {
            'devicetype': 'u2f',
            'name': 'Foo'
        })
        assert 'alert-danger' in r.rendered_content

    def test_create_u2f(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'u2f',
                'name': 'Foo'
            })
            d = U2FDevice.objects.first()
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
            'token': str(totp.token())
        }, follow=True)
        d.refresh_from_db()
        assert d.confirmed
        assert 'alert-success' in r.rendered_content

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
        assert 'alert-danger' in r.rendered_content
        d.refresh_from_db()
        assert not d.confirmed

    def test_confirm_u2f_failed(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'u2f',
                'name': 'Foo'
            }, follow=True)
        d = U2FDevice.objects.first()
        r = self.client.post('/control/settings/2fa/u2f/{}/confirm'.format(d.pk), {
            'token': 'FOO'
        }, follow=True)
        assert 'alert-danger' in r.rendered_content
        d.refresh_from_db()
        assert not d.confirmed

    def test_confirm_u2f_success(self):
        with mocker_context() as mocker:
            mocker.patch('django.http.request.HttpRequest.is_secure')
            self.client.post('/control/settings/2fa/add', {
                'devicetype': 'u2f',
                'name': 'Foo'
            }, follow=True)

        m = monkeypatch.monkeypatch()
        m.setattr("u2flib_server.u2f.complete_register", lambda *args, **kwargs: (JSONDict({}), None))

        d = U2FDevice.objects.first()
        r = self.client.post('/control/settings/2fa/u2f/{}/confirm'.format(d.pk), {
            'token': 'FOO'
        }, follow=True)
        d.refresh_from_db()
        assert d.confirmed
        assert 'alert-success' in r.rendered_content

        m.undo()
