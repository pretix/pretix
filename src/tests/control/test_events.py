import datetime
from decimal import Decimal

import pytz
from i18nfield.strings import LazyI18nString
from pytz import timezone
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import (
    Event, EventPermission, Organizer, OrganizerPermission, User,
)
from pretix.testutils.mock import mocker_context


class EventsTest(SoupTest):
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
        self.event2 = Event.objects.create(
            organizer=self.orga1, name='31C3', slug='31c3',
            date_from=datetime.datetime(2014, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.event3 = Event.objects.create(
            organizer=self.orga2, name='MRMCD14', slug='mrmcd14',
            date_from=datetime.datetime(2014, 9, 5, tzinfo=datetime.timezone.utc),
        )
        OrganizerPermission.objects.create(organizer=self.orga1, user=self.user)
        EventPermission.objects.create(event=self.event1, user=self.user, can_change_items=True,
                                       can_change_settings=True)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_event_list(self):
        doc = self.get_doc('/control/events/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("30C3", tabletext)
        self.assertNotIn("31C3", tabletext)
        self.assertNotIn("MRMCD14", tabletext)

    def test_settings(self):
        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=date_to]")[0]['value'] = "2013-12-30 17:00:00"
        doc.select("[name=settings-max_items_per_order]")[0]['value'] = "12"

        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        assert doc.select("[name=date_to]")[0]['value'] == "2013-12-30 17:00:00"
        assert doc.select("[name=settings-max_items_per_order]")[0]['value'] == "12"

    def test_settings_timezone(self):
        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=date_to]")[0]['value'] = "2013-12-30 17:00:00"
        doc.select("[name=settings-max_items_per_order]")[0]['value'] = "12"
        doc.select("[name=settings-timezone]")[0]['value'] = "Asia/Tokyo"
        doc.find('option', {"value": "Asia/Tokyo"})['selected'] = 'selected'
        doc.find('option', {"value": "UTC"}).attrs.pop('selected')

        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        # date_to should not be changed even though the timezone is changed
        assert doc.select("[name=date_to]")[0]['value'] == "2013-12-30 17:00:00"
        assert doc.find('option', {"value": "Asia/Tokyo"})['selected'] == "selected"
        assert doc.select("[name=settings-max_items_per_order]")[0]['value'] == "12"

        self.event1.refresh_from_db()
        # Asia/Tokyo -> GMT+9
        assert self.event1.date_to.strftime('%Y-%m-%d %H:%M:%S') == "2013-12-30 08:00:00"
        assert self.event1.settings.timezone == 'Asia/Tokyo'

    def test_plugins(self):
        doc = self.get_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug))
        self.assertIn("PayPal", doc.select(".form-plugins")[0].text)
        self.assertIn("Enable", doc.select("[name=plugin:pretix.plugins.paypal]")[0].text)

        doc = self.post_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug),
                            {'plugin:pretix.plugins.paypal': 'enable'})
        self.assertIn("Disable", doc.select("[name=plugin:pretix.plugins.paypal]")[0].text)

        doc = self.post_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug),
                            {'plugin:pretix.plugins.paypal': 'disable'})
        self.assertIn("Enable", doc.select("[name=plugin:pretix.plugins.paypal]")[0].text)

    def test_live_disable(self):
        self.event1.live = False
        self.event1.save()
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'live': 'false'})
        self.event1.refresh_from_db()
        assert not self.event1.live

    def test_live_ok(self):
        self.event1.items.create(name='Test', default_price=5)
        self.event1.settings.set('payment_banktransfer__enabled', True)
        self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select(".btn-primary"))
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'live': 'true'})
        self.event1.refresh_from_db()
        assert self.event1.live

    def test_live_dont_require_payment_method_free(self):
        self.event1.items.create(name='Test', default_price=0)
        self.event1.settings.set('payment_banktransfer__enabled', False)
        self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select(".btn-primary"))

    def test_live_require_payment_method(self):
        self.event1.items.create(name='Test', default_price=5)
        self.event1.settings.set('payment_banktransfer__enabled', False)
        self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select(".btn-primary")) == 0

    def test_live_require_a_quota(self):
        self.event1.settings.set('payment_banktransfer__enabled', True)
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select(".btn-primary")) == 0

    def test_payment_settings(self):
        self.get_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug))
        self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_banktransfer__enabled': 'true',
            'payment_banktransfer__fee_abs': '12.23',
            'payment_banktransfer_bank_details_0': 'Test',
            'settings-payment_term_days': '2',
            'settings-tax_rate_default': '19.00',
        })
        self.event1.settings._flush()
        assert self.event1.settings.get('payment_banktransfer__enabled', as_type=bool)
        assert self.event1.settings.get('payment_banktransfer__fee_abs', as_type=Decimal) == Decimal('12.23')

    def test_payment_settings_dont_require_fields_of_inactive_providers(self):
        doc = self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'settings-tax_rate_default': '19.00',
            'settings-payment_term_days': '2'
        }, follow=True)
        assert doc.select('.alert-success')

    def test_payment_settings_require_fields_of_active_providers(self):
        doc = self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_banktransfer__enabled': 'true',
            'payment_banktransfer__fee_abs': '12.23',
            'settings-payment_term_days': '2',
            'settings-tax_rate_default': '19.00',
        })
        assert doc.select('.alert-danger')

    def test_payment_settings_last_date_payment_after_presale_end(self):
        self.event1.presale_end = datetime.datetime.now()
        self.event1.save(update_fields=['presale_end'])
        doc = self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_banktransfer__enabled': 'true',
            'payment_banktransfer__fee_abs': '12.23',
            'payment_banktransfer_bank_details_0': 'Test',
            'settings-payment_term_days': '2',
            'settings-payment_term_last': (self.event1.presale_end - datetime.timedelta(1)).strftime('%Y-%m-%d'),
            'settings-tax_rate_default': '19.00',
        })
        assert doc.select('.alert-danger')
        self.event1.presale_end = None
        self.event1.save(update_fields=['presale_end'])

    def test_invoice_settings(self):
        doc = self.get_doc('/control/event/%s/%s/settings/invoice' % (self.orga1.slug, self.event1.slug))
        data = extract_form_fields(doc.select("form")[0])
        data['invoice_address_required'] = 'on'
        doc = self.post_doc('/control/event/%s/%s/settings/invoice' % (self.orga1.slug, self.event1.slug),
                            data, follow=True)
        assert doc.select('.alert-success')
        self.event1.settings._flush()
        assert self.event1.settings.get('invoice_address_required', as_type=bool)

    def test_display_settings(self):
        with mocker_context() as mocker:
            mocked = mocker.patch('pretix.presale.style.regenerate_css.apply_async')

            doc = self.get_doc('/control/event/%s/%s/settings/display' % (self.orga1.slug, self.event1.slug))
            data = extract_form_fields(doc.select("form")[0])
            data['primary_color'] = '#FF0000'
            doc = self.post_doc('/control/event/%s/%s/settings/display' % (self.orga1.slug, self.event1.slug),
                                data, follow=True)
            assert doc.select('.alert-success')
            self.event1.settings._flush()
            assert self.event1.settings.get('primary_color') == '#FF0000'
            mocked.assert_any_call(args=(self.event1.pk,))

    def test_email_settings(self):
        with mocker_context() as mocker:
            mocked = mocker.patch('pretix.base.email.CustomSMTPBackend.test')

            doc = self.get_doc('/control/event/%s/%s/settings/email' % (self.orga1.slug, self.event1.slug))
            data = extract_form_fields(doc.select("form")[0])
            data['test'] = '1'
            doc = self.post_doc('/control/event/%s/%s/settings/email' % (self.orga1.slug, self.event1.slug),
                                data, follow=True)
            assert doc.select('.alert-success')
            self.event1.settings._flush()
            assert mocked.called

    def test_ticket_settings(self):
        doc = self.get_doc('/control/event/%s/%s/settings/tickets' % (self.orga1.slug, self.event1.slug))
        data = extract_form_fields(doc.select("form")[0])
        data['ticket_download'] = 'on'
        data['ticketoutput_testdummy__enabled'] = 'on'
        doc = self.post_doc('/control/event/%s/%s/settings/tickets' % (self.orga1.slug, self.event1.slug),
                            data, follow=True)
        self.event1.settings._flush()
        assert self.event1.settings.get('ticket_download', as_type=bool)

    def test_create_event_unauthorized(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga2.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select(".alert-danger")

    def test_create_invalid_default_language(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('de',)
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from': '2016-12-27 10:00:00',
            'basics-date_to': '2016-12-30 19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start': '2016-11-01 10:00:00',
            'basics-presale_end': '2016-11-30 18:00:00',
        })
        assert doc.select(".alert-danger")

    def test_create_duplicate_slug(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('de', 'en')
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '31c3',
            'basics-date_from': '2016-12-27 10:00:00',
            'basics-date_to': '2016-12-30 19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start': '2016-11-01 10:00:00',
            'basics-presale_end': '2016-11-30 18:00:00',
        })
        assert doc.select(".alert-danger")

    def test_create_event_success(self):
        doc = self.get_doc('/control/events/add')
        tabletext = doc.select("form")[0].text
        self.assertIn("CCC", tabletext)
        self.assertNotIn("MRM", tabletext)

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select("#id_basics-name_0")
        assert doc.select("#id_basics-name_1")

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from': '2016-12-27 10:00:00',
            'basics-date_to': '2016-12-30 19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start': '2016-11-01 10:00:00',
            'basics-presale_end': '2016-11-30 18:00:00',
        })

        assert doc.select("#id_copy-copy_from_event_1")

        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'copy-copy_from_event': ''
        })

        ev = Event.objects.get(slug='33c3')
        assert ev.name == LazyI18nString({'de': '33C3', 'en': '33C3'})
        assert ev.settings.locales == ['en', 'de']
        assert ev.settings.locale == 'en'
        assert ev.currency == 'EUR'
        assert ev.settings.timezone == 'Europe/Berlin'
        assert ev.organizer == self.orga1
        assert ev.location == LazyI18nString({'de': 'Hamburg', 'en': 'Hamburg'})
        assert EventPermission.objects.filter(event=ev, user=self.user).exists()

        berlin_tz = timezone('Europe/Berlin')
        assert ev.date_from == berlin_tz.localize(datetime.datetime(2016, 12, 27, 10, 0, 0)).astimezone(pytz.utc)
        assert ev.date_to == berlin_tz.localize(datetime.datetime(2016, 12, 30, 19, 0, 0)).astimezone(pytz.utc)
        assert ev.presale_start == berlin_tz.localize(datetime.datetime(2016, 11, 1, 10, 0, 0)).astimezone(pytz.utc)
        assert ev.presale_end == berlin_tz.localize(datetime.datetime(2016, 11, 30, 18, 0, 0)).astimezone(pytz.utc)

    def test_create_event_only_date_from(self):
        # date_to, presale_start & presale_end are optional fields
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from': '2016-12-27 10:00:00',
            'basics-date_to': '',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-locale': 'en',
            'basics-timezone': 'UTC',
            'basics-presale_start': '',
            'basics-presale_end': '',
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'copy-copy_from_event': ''
        })

        ev = Event.objects.get(slug='33c3')
        assert ev.name == LazyI18nString({'en': '33C3'})
        assert ev.settings.locales == ['en']
        assert ev.settings.locale == 'en'
        assert ev.currency == 'EUR'
        assert ev.settings.timezone == 'UTC'
        assert ev.organizer == self.orga1
        assert ev.location == LazyI18nString({'en': 'Hamburg'})
        assert EventPermission.objects.filter(event=ev, user=self.user).exists()
        assert ev.date_from == datetime.datetime(2016, 12, 27, 10, 0, 0, tzinfo=pytz.utc)
        assert ev.date_to is None
        assert ev.presale_start is None
        assert ev.presale_end is None

    def test_create_event_missing_date_from(self):
        # date_from is mandatory
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from': '',
            'basics-date_to': '2016-12-30 19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start': '2016-11-20 11:00:00',
            'basics-presale_end': '2016-11-24 18:00:00',
        })
        assert doc.select(".alert-danger")
