#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from django.db import transaction
from django.test.utils import override_settings
from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def class_monkeypatch(request, monkeypatch):
    request.cls.monkeypatch = monkeypatch


@pytest.mark.usefixtures("class_monkeypatch")
class OrganizerTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
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
        called = False

        def set_called(*args, **kwargs):
            nonlocal called
            called = True

        self.monkeypatch.setattr("pretix.presale.style.regenerate_organizer_css.apply_async", set_called)
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
        assert called

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
