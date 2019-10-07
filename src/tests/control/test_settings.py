import datetime
import json
import re

from django_scopes import scopes_disabled
from tests.base import SoupTest

from pretix.base.models import Event, Organizer, Team, User


class MailSettingPreviewTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        # event with locale
        self.locale_event = Event.objects.create(
            organizer=self.orga1, name={'en': '40C4-en', 'de-informal': '40C4-de'}, slug='40c4',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.locale_event.settings.locales = ['en', 'de-informal']
        self.locale_event.save()
        t = Team.objects.create(organizer=self.orga1, can_change_items=True, can_change_event_settings=True)
        t.members.add(self.user)
        t.limit_events.add(self.locale_event)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.target = '/control/event/{}/{}/settings/email/preview'

    def test_permission(self):
        with scopes_disabled():
            self.event2 = Event.objects.create(
                organizer=self.orga2, name='30M3', slug='30m3',
                date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            )
        response = self.client.post(self.target.format(
            self.orga2.slug, self.event2.slug), {
            'test': 'test1'
        })
        assert response.status_code == 404

    def test_missing_item_key(self):
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'dummy',
            'mail_text_order_free_0': 'sss',
            'mail_text_order_free_1': 'ttt'
        })
        assert response.status_code == 400

    def test_invalid_item_field(self):
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_free',
            'mail_text_order_free_w': 'sss'
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_free'
        assert len(res['msgs']) == 0

    def test_invalid_language_index(self):
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_free',
            'mail_text_order_free_1': 'sss'
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_free'
        assert len(res['msgs']) == 0

    def test_no_item_field(self):
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'mail_text_order_free_0': 'sss'
        })
        assert response.status_code == 400

    def test_only_en(self):
        dummy_text = 'This is dummy sentence for test'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_free',
            'mail_text_order_free_0': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_free'
        assert len(res['msgs']) == 1
        assert dummy_text in res['msgs']['en']

    def test_multiple_languages(self):
        dummy_text = 'This is dummy sentence for test'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_free',
            'mail_text_order_free_0': dummy_text,
            'mail_text_order_free_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_free'
        assert len(res['msgs']) == 2
        assert dummy_text in res['msgs']['en']
        assert dummy_text in res['msgs']['de-informal']

    def test_i18n_placeholders(self):
        dummy_text = '{event}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_placed',
            'mail_text_order_placed_0': dummy_text,
            'mail_text_order_placed_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_placed'
        assert len(res['msgs']) == 2
        assert self.locale_event.name['en'] in res['msgs']['en']
        assert self.locale_event.name['de-informal'] in res['msgs']['de-informal']

    def test_i18n_locale_order(self):
        self.locale_event.settings.locales = ['de-informal', 'en']
        self.locale_event.save()
        dummy_text = '{event}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_placed',
            'mail_text_order_placed_0': dummy_text,
            'mail_text_order_placed_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_placed'
        assert len(res['msgs']) == 2
        assert self.locale_event.name['de-informal'] in res['msgs']['de-informal']
        assert self.locale_event.name['en'] in res['msgs']['en']

    def test_mail_text_order_placed(self):
        text = '{event}{total}{currency}{expire_date}{payment_info}{url}{invoice_name}{invoice_company}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_placed',
            'mail_text_order_placed_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_placed'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_order_paid(self):
        text = '{event}{url}{invoice_name}{invoice_company}{payment_info}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_paid',
            'mail_text_order_paid_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_paid'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_order_free(self):
        text = '{event}{url}{invoice_name}{invoice_company}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_free',
            'mail_text_order_free_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_free'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_resend_link(self):
        text = '{event}{url}{invoice_name}{invoice_company}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_resend_link',
            'mail_text_resend_link_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_resend_link'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_resend_all_links(self):
        text = '{event}{orders}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_resend_all_links',
            'mail_text_resend_all_links_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_resend_all_links'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_order_changed(self):
        text = '{event}{url}{invoice_name}{invoice_company}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_changed',
            'mail_text_order_changed_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_changed'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_order_expire_warning(self):
        text = '{event}{url}{expire_date}{invoice_name}{invoice_company}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_expire_warning',
            'mail_text_order_expire_warning_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_expire_warning'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_waiting_list(self):
        text = '{event}{url}{product}{hours}{code}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_waiting_list',
            'mail_text_waiting_list_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_waiting_list'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_mail_text_order_canceled(self):
        text = '{event}{code}{url}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_order_canceled',
            'mail_text_order_canceled_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_canceled'
        assert len(res['msgs']) == 1
        assert re.match('.*{.*}.*', res['msgs']['en']) is None

    def test_unsupported_placeholders(self):
        text = '{event1}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.event1.slug), {
            'item': 'mail_text_waiting_list',
            'mail_text_waiting_list_0': text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_waiting_list'
        assert len(res['msgs']) == 1
        assert text in res['msgs']['en']

    def test_localized_date(self):
        dummy_text = '{expire_date}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_placed',
            'mail_text_order_placed_0': dummy_text,
            'mail_text_order_placed_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_placed'
        assert len(res['msgs']) == 2
        assert res['msgs']['en'] != res['msgs']['de-informal']

    def test_localized_expire_date(self):
        dummy_text = '{expire_date}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_expire_warning',
            'mail_text_order_expire_warning_0': dummy_text,
            'mail_text_order_expire_warning_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_expire_warning'
        assert len(res['msgs']) == 2
        assert res['msgs']['en'] != res['msgs']['de-informal']

    def test_localized_payment_info(self):
        dummy_text = '{payment_info}'
        response = self.client.post(self.target.format(
            self.orga1.slug, self.locale_event.slug), {
            'item': 'mail_text_order_paid',
            'mail_text_order_paid_0': dummy_text,
            'mail_text_order_paid_2': dummy_text
        })
        assert response.status_code == 200
        res = json.loads(response.content.decode())
        assert res['item'] == 'mail_text_order_paid'
        assert len(res['msgs']) == 2
        assert res['msgs']['en'] != res['msgs']['de-informal']
