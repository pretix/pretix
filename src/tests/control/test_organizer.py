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
import datetime
from smtplib import SMTPResponseException

import pytest
import responses
from django.conf import settings
from django.db import transaction
from django.test.utils import override_settings
from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Organizer, OutgoingMail, Team, User


@pytest.fixture
def class_monkeypatch(request, monkeypatch):
    request.cls.monkeypatch = monkeypatch


@pytest.mark.usefixtures("class_monkeypatch")
class OrganizerTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc', plugins='pretix.plugins.banktransfer')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm', plugins='pretix.plugins.banktransfer')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy'
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True, can_change_organizer_settings=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_organizer_list(self):
        doc = self.get_doc('/control/organizers/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("CCC", tabletext)
        self.assertNotIn("MRM", tabletext)

    def test_organizer_detail(self):
        doc = self.get_doc('/control/organizer/ccc/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("30C3", tabletext)

    def test_organizer_settings(self):
        doc = self.get_doc('/control/organizer/%s/edit' % (self.orga1.slug,))
        doc.select("[name=name]")[0]['value'] = "CCC e.V."

        doc = self.post_doc('/control/organizer/%s/edit' % (self.orga1.slug,),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        assert doc.select("[name=name]")[0]['value'] == "CCC e.V."
        self.orga1.refresh_from_db()
        assert self.orga1.name == "CCC e.V."

    def test_organizer_display_settings(self):
        assert not self.orga1.settings.presale_css_checksum
        doc = self.get_doc('/control/organizer/%s/edit' % (self.orga1.slug,))
        doc.select("[name=settings-primary_color]")[0]['value'] = "#33c33c"

        with transaction.atomic():
            doc = self.post_doc('/control/organizer/%s/edit' % (self.orga1.slug,),
                                extract_form_fields(doc.select('.container-fluid form')[0]))
            assert len(doc.select(".alert-success")) > 0
            assert doc.select("[name=settings-primary_color]")[0]['value'] == "#33c33c"
        self.orga1.settings.flush()
        assert self.orga1.settings.primary_color == "#33c33c"

    def test_email_settings(self):
        doc = self.get_doc('/control/organizer/%s/settings/email' % self.orga1.slug)
        data = extract_form_fields(doc.select("form")[0])
        data['mail_from_name'] = 'test'
        doc = self.post_doc('/control/organizer/%s/settings/email' % self.orga1.slug,
                            data, follow=True)
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        assert self.orga1.settings.mail_from_name == "test"

    def test_email_setup_system(self):
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'system'
            },
            follow=True
        )
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        assert "mail_from" not in self.orga1.settings._cache()
        assert not self.orga1.settings.smtp_use_custom

    @override_settings(MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED=True, MAIL_CUSTOM_SENDER_SPF_STRING=False)
    def test_email_setup_simple_with_verification(self):
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'simple',
                'simple-mail_from': 'test@test.pretix.dev',
            },
            follow=True
        )
        self.orga1.settings.flush()
        assert "mail_from" not in self.orga1.settings._cache()
        data = extract_form_fields(doc.select("form")[0])
        data['verification'] = self.client.session[
            f'sender_mail_verification_code_/control/organizer/{self.orga1.slug}/settings/email/setup_test@test.pretix.dev'
        ]
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            data,
            follow=True
        )
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        assert self.orga1.settings.mail_from == 'test@test.pretix.dev'

    @override_settings(MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED=True, MAIL_CUSTOM_SENDER_SPF_STRING=False)
    def test_email_setup_simple_with_verification_wrong_code(self):
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'simple',
                'simple-mail_from': 'test@test.pretix.dev',
            },
            follow=True
        )
        self.orga1.settings.flush()
        assert "mail_from" not in self.orga1.settings._cache()
        data = extract_form_fields(doc.select("form")[0])
        data['verification'] = 'AAAA'
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            data,
            follow=True
        )
        assert doc.select('.alert-danger')
        self.orga1.settings.flush()
        assert "mail_from" not in self.orga1.settings._cache()

    @staticmethod
    def _fake_spf_record(hostname):
        return {
            'test.pretix.dev': 'v=spf1 a mx include:level2.pretix.dev ~all',
            'level2.pretix.dev': 'v=spf1 a mx +include:level3.pretix.dev include:spftest.pretix.dev '
                                 '-include:level4.pretix.dev ~all',
            'level3.pretix.dev': 'v=spf1 a mx include:test2.pretix.dev ~all',
            'level4.pretix.dev': 'v=spf1 a mx include:test3.pretix.dev ~all',
            'test2.pretix.dev': None,
            'test3.pretix.dev': None,
            'spftest.pretix.dev': None,
        }[hostname]

    @override_settings(MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED=False, MAIL_CUSTOM_SENDER_SPF_STRING="include:spftest.pretix.dev include:test2.pretix.dev")
    def test_email_setup_no_verification_spf_success(self):
        self.monkeypatch.setattr("pretix.control.views.mailsetup.get_spf_record", OrganizerTest._fake_spf_record)
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'simple',
                'simple-mail_from': 'test@test.pretix.dev',
            },
            follow=True
        )
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        # not yet saved
        assert "mail_from" not in self.orga1.settings._cache()
        data = extract_form_fields(doc.select("form")[0])
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            data,
            follow=True
        )
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        assert self.orga1.settings.mail_from == 'test@test.pretix.dev'

    @override_settings(MAIL_CUSTOM_SENDER_VERIFICATION_REQUIRED=False, MAIL_CUSTOM_SENDER_SPF_STRING="include:spftest.pretix.dev include:test3.pretix.dev")
    def test_email_setup_no_verification_spf_warning(self):
        self.monkeypatch.setattr("pretix.control.views.mailsetup.get_spf_record", OrganizerTest._fake_spf_record)
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'simple',
                'simple-mail_from': 'test@test.pretix.dev',
            },
            follow=True
        )
        assert doc.select('.alert-danger')
        self.orga1.settings.flush()
        # not yet saved
        assert "mail_from" not in self.orga1.settings._cache()

    def test_email_setup_smtp(self):
        self.monkeypatch.setattr("pretix.base.email.test_custom_smtp_backend", lambda b, a: None)
        self.monkeypatch.setattr("socket.gethostbyname", lambda h: "8.8.8.8")
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'smtp',
                'smtp-mail_from': 'test@test.pretix.dev',
                'smtp-smtp_host': 'test.pretix.dev',
                'smtp-smtp_port': '587',
            },
            follow=True
        )
        assert doc.select('.alert-success')
        # not yet saved
        self.orga1.settings.flush()
        assert "smtp_use_custom" not in self.orga1.settings._cache()
        data = extract_form_fields(doc.select("form")[0])
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            data,
            follow=True
        )
        assert doc.select('.alert-success')
        self.orga1.settings.flush()
        assert self.orga1.settings.mail_from == 'test@test.pretix.dev'
        assert self.orga1.settings.smtp_host == 'test.pretix.dev'
        assert self.orga1.settings.smtp_port == 587
        assert self.orga1.settings.smtp_use_custom

    def test_email_setup_smtp_failure(self):
        def fail(a, b):
            raise SMTPResponseException(400, 'Auth denied')
        self.monkeypatch.setattr("pretix.base.email.test_custom_smtp_backend", fail)
        self.monkeypatch.setattr("socket.gethostbyname", lambda h: "8.8.8.8")
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'smtp',
                'smtp-mail_from': 'test@test.pretix.dev',
                'smtp-smtp_host': 'test.pretix.dev',
                'smtp-smtp_port': '587',
            },
            follow=True
        )
        assert 'Auth denied' in doc.select('.alert-danger')[0].text
        # not yet saved
        self.orga1.settings.flush()
        assert "smtp_use_custom" not in self.orga1.settings._cache()
        assert "mail_from" not in self.orga1.settings._cache()

    def test_email_setup_do_not_allow_private_ip_by_default(self):
        doc = self.post_doc(
            '/control/organizer/%s/settings/email/setup' % self.orga1.slug,
            {
                'mode': 'simple',
                'smtp-mail_from': 'test@test.pretix.dev',
                'smtp-smtp_host': '10.0.1.1',
                'smtp-smtp_port': '587',
            },
            follow=True
        )
        assert doc.select('.has-error')
        # not yet saved
        self.orga1.settings.flush()
        assert "smtp_use_custom" not in self.orga1.settings._cache()
        assert "mail_from" not in self.orga1.settings._cache()

    @responses.activate
    def test_create_sso_provider(self):
        conf = {
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "userinfo_endpoint": "https://example.com/userinfo",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code"],
            "scopes_supported": ["openid", "email", "profile"],
            "claims_supported": ["email", "sub"]
        }
        responses.add(
            responses.GET,
            "https://example.com/provider/.well-known/openid-configuration",
            json=conf
        )
        doc = self.post_doc(
            '/control/organizer/%s/ssoprovider/add' % self.orga1.slug,
            {
                'name_0': 'OIDC',
                'button_label_0': 'Log in with OIDC',
                'method': 'oidc',
                'config_oidc_base_url': 'https://example.com/provider',
                'config_oidc_client_id': 'aaaa',
                'config_oidc_client_secret': 'bbbb',
                'config_oidc_scope': 'openid email',
                'config_oidc_email_field': 'email',
                'config_oidc_uid_field': 'sub',
            },
            follow=True
        )
        assert not doc.select('.has-error, .alert-danger')
        with scopes_disabled():
            p = self.orga1.sso_providers.get()
            assert p.configuration['scope'] == 'openid email'
            assert p.configuration['provider_config'] == conf

    def test_sales_channel_add_edit_remove(self):
        doc = self.post_doc(
            '/control/organizer/%s/channel/add?type=api' % self.orga1.slug,
            {
                'label_0': 'API 1',
                'identifier': 'custom',
            },
            follow=True
        )
        assert not doc.select('.has-error, .alert-danger')
        with scopes_disabled():
            assert str(self.orga1.sales_channels.get(identifier="api.custom").label) == "API 1"

        doc = self.post_doc(
            '/control/organizer/%s/channel/api.custom/edit' % self.orga1.slug,
            {
                'label_0': 'API 2',
            },
            follow=True
        )
        assert not doc.select('.has-error, .alert-danger')
        with scopes_disabled():
            assert str(self.orga1.sales_channels.get(identifier="api.custom").label) == "API 2"

        doc = self.post_doc(
            '/control/organizer/%s/channel/api.custom/delete' % self.orga1.slug,
            {},
            follow=True
        )
        assert not doc.select('.has-error, .alert-danger')
        with scopes_disabled():
            assert not self.orga1.sales_channels.filter(identifier="api.custom").exists()

    def test_sales_channel_add_invalid_type(self):
        doc = self.post_doc(
            '/control/organizer/%s/channel/add?type=web' % self.orga1.slug,
            {
                'label_0': 'API 1',
                'identifier': 'custom',
            },
            follow=True
        )
        assert doc.select('.large-link-group')

    def test_sales_channel_delete_invalid(self):
        doc = self.post_doc(
            '/control/organizer/%s/channel/web/delete' % self.orga1.slug,
            {
                'label_0': 'API 1',
                'identifier': 'custom',
            },
            follow=True
        )
        assert doc.select('.alert-danger')
        with scopes_disabled():
            assert self.orga1.sales_channels.filter(identifier="web").exists()

    def test_plugins(self):
        doc = self.get_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug)
        self.assertIn("Stripe", doc.select(".form-plugins")[0].text)
        self.assertIn("Enable", doc.select("[name=\"plugin:tests.testdummyorga\"]")[0].text)
        self.assertIn("Enable", doc.select("[name=\"plugin:tests.testdummyhybrid\"]")[0].text)
        assert not doc.select("[name=\"plugin:pretix.plugins.stripe\"]")
        assert not doc.select("[name=\"plugin:tests.testdummy\"]")
        assert not doc.select("[name=\"plugin:tests.testdummyrestricted\"]")
        assert not doc.select("[name=\"plugin:tests.testdummyorgarestricted\"]")
        assert not doc.select("[name=\"plugin:tests.testdummyhidden\"]")

        doc = self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                            {'plugin:tests.testdummyorga': 'enable'})
        self.assertIn("Disable", doc.select("[name=\"plugin:tests.testdummyorga\"]")[0].text)

        doc = self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                            {'plugin:tests.testdummyhybrid': 'enable'})
        self.assertIn("Events with plugin testdummyhybrid", doc.select("h1")[0].text)
        self.orga1.refresh_from_db()
        assert "tests.testdummyhybrid" in self.orga1.get_plugins()

        doc = self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                            {'plugin:tests.testdummyhybrid': 'disable'})
        self.assertIn("Enable", doc.select("[name=\"plugin:tests.testdummyhybrid\"]")[0].text)

        self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                      {'plugin:tests.testdummy': 'enable'})
        self.orga1.refresh_from_db()
        assert "tests.testdummy" not in self.orga1.get_plugins()

        self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                      {'plugin:tests.testdummyorgarestricted': 'enable'})
        self.orga1.refresh_from_db()
        assert "testdummyorgarestricted" not in self.orga1.get_plugins()

        self.orga1.settings.allowed_restricted_plugins = ["tests.testdummyorgarestricted"]

        self.post_doc('/control/organizer/%s/settings/plugins' % self.orga1.slug,
                      {'plugin:tests.testdummyorgarestricted': 'enable'})
        self.orga1.refresh_from_db()
        assert "tests.testdummyorgarestricted" in self.orga1.get_plugins()

    def test_plugin_events(self):
        resp = self.client.get('/control/organizer/%s/settings/plugins/tests.testdummyorga/events' % self.orga1.slug)
        assert resp.status_code == 404
        assert b"only be enabled for the entire organizer account" in resp.content

        resp = self.client.get(
            '/control/organizer/%s/settings/plugins/tests.testdummyrestricted/events' % self.orga1.slug)
        assert resp.status_code == 404
        assert b"currently not allowed" in resp.content

        resp = self.client.get('/control/organizer/%s/settings/plugins/tests.testdummyhybrid/events' % self.orga1.slug)
        assert resp.status_code == 404
        assert b"currently not active on the organizer" in resp.content

        resp = self.client.get('/control/organizer/%s/settings/plugins/pretix.plugins.stripe/events' % self.orga1.slug)
        assert resp.status_code == 200

        resp = self.client.post('/control/organizer/%s/settings/plugins/pretix.plugins.stripe/events' % self.orga1.slug,
                                {'events': self.event1.pk})
        assert resp.status_code == 302
        self.event1.refresh_from_db()
        assert 'pretix.plugins.stripe' in self.event1.get_plugins()
        assert 'pretix.plugins.banktransfer' in self.event1.get_plugins()

        resp = self.client.post('/control/organizer/%s/settings/plugins/pretix.plugins.banktransfer/events' % self.orga1.slug,
                                {})
        assert resp.status_code == 302
        self.event1.refresh_from_db()
        assert 'pretix.plugins.banktransfer' not in self.event1.get_plugins()
        assert 'pretix.plugins.stripe' in self.event1.get_plugins()

    def test_outgoing_mails_list_and_detail(self):
        m1 = OutgoingMail.objects.create(
            organizer=self.orga1,
            to=['rightrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        m2 = OutgoingMail.objects.create(
            organizer=self.orga2,
            to=['wrongrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        resp = self.client.get('/control/organizer/%s/outgoingmails' % self.orga1.slug)
        assert resp.status_code == 200
        assert b"rightrecipient@example.com" in resp.content
        assert b"wrongrecipient@example.com" not in resp.content

        resp = self.client.get('/control/organizer/%s/outgoingmails?status=queued' % self.orga1.slug)
        assert resp.status_code == 200
        assert b"rightrecipient@example.com" in resp.content
        resp = self.client.get('/control/organizer/%s/outgoingmails?status=sent' % self.orga1.slug)
        assert resp.status_code == 200
        assert b"rightrecipient@example.com" not in resp.content

        if 'postgresql' in settings.DATABASES['default']['ENGINE']:
            resp = self.client.get('/control/organizer/%s/outgoingmails?query=RIGHTrecipient@example.com' % self.orga1.slug)
            assert resp.status_code == 200
            assert b"rightrecipient@example.com" in resp.content
            resp = self.client.get('/control/organizer/%s/outgoingmails?query=wrongrecipient@example.com' % self.orga1.slug)
            assert resp.status_code == 200
            assert b"rightrecipient@example.com" not in resp.content

        resp = self.client.get('/control/organizer/%s/outgoingmail/%d/' % (self.orga1.slug, m1.pk))
        assert resp.status_code == 200
        assert b"rightrecipient@example.com" in resp.content

        resp = self.client.get('/control/organizer/%s/outgoingmail/%d/' % (self.orga1.slug, m2.pk))
        assert resp.status_code == 404

    def test_outgoing_mails_retry(self):
        m1 = OutgoingMail.objects.create(
            organizer=self.orga1,
            status=OutgoingMail.STATUS_SENT,
            to=['rightrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        m2 = OutgoingMail.objects.create(
            organizer=self.orga1,
            status=OutgoingMail.STATUS_FAILED,
            to=['rightrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        resp = self.client.post(
            '/control/organizer/%s/outgoingmail/bulk_action' % self.orga1.slug,
            data={
                "action": "retry",
                "outgoingmail": [m1.pk, m2.pk]
            }
        )
        assert resp.status_code == 302
        m1.refresh_from_db()
        m2.refresh_from_db()
        assert m1.status == OutgoingMail.STATUS_SENT
        assert m2.status in (OutgoingMail.STATUS_SENT, OutgoingMail.STATUS_QUEUED)

    def test_outgoing_mails_abort(self):
        m1 = OutgoingMail.objects.create(
            organizer=self.orga1,
            status=OutgoingMail.STATUS_SENT,
            to=['rightrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        m2 = OutgoingMail.objects.create(
            organizer=self.orga1,
            status=OutgoingMail.STATUS_QUEUED,
            to=['rightrecipient@example.com'],
            subject='Test',
            body_plain='Test',
            sender='sender@example.com',
            headers={},
        )
        resp = self.client.post(
            '/control/organizer/%s/outgoingmail/bulk_action' % self.orga1.slug,
            data={
                "action": "abort",
                "__ALL": "on",
            }
        )
        assert resp.status_code == 302
        m1.refresh_from_db()
        m2.refresh_from_db()
        assert m1.status == OutgoingMail.STATUS_SENT
        assert m2.status == OutgoingMail.STATUS_ABORTED
