import datetime
import time
from decimal import Decimal

import pytz
from django.utils.timezone import now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString
from pytz import timezone
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import (
    Event, Order, OrderPosition, Organizer, SubEvent, Team, User,
)
from pretix.base.models.items import SubEventItem
from pretix.testutils.mock import mocker_context


class EventsTest(SoupTest):
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
        self.event2 = Event.objects.create(
            organizer=self.orga1, name='31C3', slug='31c3',
            date_from=datetime.datetime(2014, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.event3 = Event.objects.create(
            organizer=self.orga2, name='MRMCD14', slug='mrmcd14',
            date_from=datetime.datetime(2014, 9, 5, tzinfo=datetime.timezone.utc),
        )

        self.team1 = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                         can_change_items=True)
        self.team1.members.add(self.user)
        self.team1.limit_events.add(self.event1)

        self.team2 = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_change_items=True,
                                         can_change_orders=True, can_change_vouchers=True)
        self.team2.members.add(self.user)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_event_list(self):
        doc = self.get_doc('/control/events/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("30C3", tabletext)
        self.assertNotIn("31C3", tabletext)
        self.assertNotIn("MRMCD14", tabletext)

    def test_convenience_organizer_redirect(self):
        resp = self.client.get('/control/event/%s/' % (self.orga1.slug))
        self.assertRedirects(resp, '/control/organizer/%s/' % (self.orga1.slug))

    def test_quick_setup_later(self):
        with scopes_disabled():
            self.event1.quotas.create(name='foo', size=2)
        resp = self.client.get('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug))
        self.assertRedirects(resp, '/control/event/%s/%s/' % (self.orga1.slug, self.event1.slug))

    def test_quick_setup_total_quota(self):
        doc = self.get_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=show_quota_left]")[0]['checked'] = "checked"
        doc.select("[name=ticket_download]")[0]['checked'] = "checked"
        doc.select("[name=contact_mail]")[0]['value'] = "test@example.org"
        doc.select("[name=payment_banktransfer__enabled]")[0]['checked'] = "checked"
        doc.select("[name=payment_banktransfer_bank_details_type]")[1]['checked'] = 'checked'
        del doc.select("[name=payment_banktransfer_bank_details_type]")[0]['checked']
        doc.select("[name*=payment_banktransfer_bank_details_0]")[0].contents[0].replace_with("Foo")
        doc.select("[name=total_quota]")[0]['value'] = "300"
        doc.select("[name=form-TOTAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-INITIAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-MIN_NUM_FORMS]")[0]['value'] = "0"
        doc.select("[name=form-MAX_NUM_FORMS]")[0]['value'] = "1000"
        doc.select("[name=form-0-name_0]")[0]['value'] = "Normal ticket"
        doc.select("[name=form-0-default_price]")[0]['value'] = "13.90"
        doc.select("[name=form-0-quota]")[0]['value'] = ""
        doc.select("[name=form-1-name_0]")[0]['value'] = "Reduced ticket"
        doc.select("[name=form-1-default_price]")[0]['value'] = "13.20"
        doc.select("[name=form-1-quota]")[0]['value'] = ""

        doc = self.post_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        self.event1.refresh_from_db()
        self.event1.settings.flush()
        assert self.event1.settings.show_quota_left
        assert self.event1.settings.contact_mail == "test@example.org"
        assert self.event1.settings.ticket_download
        assert self.event1.settings.ticketoutput_pdf__enabled
        assert self.event1.settings.payment_banktransfer__enabled
        assert self.event1.settings.get('payment_banktransfer_bank_details', as_type=LazyI18nString).localize('en') == "Foo"
        assert 'pretix.plugins.banktransfer' in self.event1.plugins
        with scopes_disabled():
            assert self.event1.items.count() == 2
            i = self.event1.items.first()
            assert str(i.name) == "Normal ticket"
            assert i.default_price == Decimal('13.90')
            i = self.event1.items.last()
            assert str(i.name) == "Reduced ticket"
            assert i.default_price == Decimal('13.20')
            assert self.event1.quotas.count() == 1
            q = self.event1.quotas.first()
            assert q.name == 'Tickets'
            assert q.size == 300
            assert q.items.count() == 2

    def test_quick_setup_single_quota(self):
        doc = self.get_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=show_quota_left]")[0]['checked'] = "checked"
        doc.select("[name=ticket_download]")[0]['checked'] = "checked"
        doc.select("[name=contact_mail]")[0]['value'] = "test@example.org"
        doc.select("[name=payment_banktransfer__enabled]")[0]['checked'] = "checked"
        doc.select("[name=payment_banktransfer_bank_details_type]")[1]['checked'] = 'checked'
        del doc.select("[name=payment_banktransfer_bank_details_type]")[0]['checked']
        doc.select("[name*=payment_banktransfer_bank_details_0]")[0].contents[0].replace_with("Foo")
        doc.select("[name=total_quota]")[0]['value'] = ""
        doc.select("[name=form-TOTAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-INITIAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-MIN_NUM_FORMS]")[0]['value'] = "0"
        doc.select("[name=form-MAX_NUM_FORMS]")[0]['value'] = "1000"
        doc.select("[name=form-0-name_0]")[0]['value'] = "Normal ticket"
        doc.select("[name=form-0-default_price]")[0]['value'] = "13.90"
        doc.select("[name=form-0-quota]")[0]['value'] = "100"
        doc.select("[name=form-1-name_0]")[0]['value'] = "Reduced ticket"
        doc.select("[name=form-1-default_price]")[0]['value'] = "13.20"
        doc.select("[name=form-1-quota]")[0]['value'] = "50"

        doc = self.post_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        self.event1.refresh_from_db()
        self.event1.settings.flush()
        assert self.event1.settings.show_quota_left
        assert self.event1.settings.contact_mail == "test@example.org"
        assert self.event1.settings.ticket_download
        assert self.event1.settings.ticketoutput_pdf__enabled
        assert self.event1.settings.payment_banktransfer__enabled
        assert self.event1.settings.get('payment_banktransfer_bank_details', as_type=LazyI18nString).localize('en') == "Foo"
        assert 'pretix.plugins.banktransfer' in self.event1.plugins
        with scopes_disabled():
            assert self.event1.items.count() == 2
            i = self.event1.items.first()
            assert str(i.name) == "Normal ticket"
            assert i.default_price == Decimal('13.90')
            i = self.event1.items.last()
            assert str(i.name) == "Reduced ticket"
            assert i.default_price == Decimal('13.20')
            assert self.event1.quotas.count() == 2
            q = self.event1.quotas.first()
            assert q.name == 'Normal ticket'
            assert q.size == 100
            assert q.items.count() == 1
            q = self.event1.quotas.last()
            assert q.name == 'Reduced ticket'
            assert q.size == 50
            assert q.items.count() == 1

    def test_quick_setup_dual_quota(self):
        doc = self.get_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=show_quota_left]")[0]['checked'] = "checked"
        doc.select("[name=ticket_download]")[0]['checked'] = "checked"
        doc.select("[name=contact_mail]")[0]['value'] = "test@example.org"
        doc.select("[name=payment_banktransfer__enabled]")[0]['checked'] = "checked"
        doc.select("[name=payment_banktransfer_bank_details_type]")[1]['checked'] = 'checked'
        del doc.select("[name=payment_banktransfer_bank_details_type]")[0]['checked']
        doc.select("[name*=payment_banktransfer_bank_details_0]")[0].contents[0].replace_with("Foo")
        doc.select("[name=total_quota]")[0]['value'] = "120"
        doc.select("[name=form-TOTAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-INITIAL_FORMS]")[0]['value'] = "2"
        doc.select("[name=form-MIN_NUM_FORMS]")[0]['value'] = "0"
        doc.select("[name=form-MAX_NUM_FORMS]")[0]['value'] = "1000"
        doc.select("[name=form-0-name_0]")[0]['value'] = "Normal ticket"
        doc.select("[name=form-0-default_price]")[0]['value'] = "13.90"
        doc.select("[name=form-0-quota]")[0]['value'] = "100"
        doc.select("[name=form-1-name_0]")[0]['value'] = "Reduced ticket"
        doc.select("[name=form-1-default_price]")[0]['value'] = "13.20"
        doc.select("[name=form-1-quota]")[0]['value'] = "50"

        doc = self.post_doc('/control/event/%s/%s/quickstart/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        self.event1.refresh_from_db()
        self.event1.settings.flush()
        assert self.event1.settings.show_quota_left
        assert self.event1.settings.contact_mail == "test@example.org"
        assert self.event1.settings.ticket_download
        assert self.event1.settings.ticketoutput_pdf__enabled
        assert self.event1.settings.payment_banktransfer__enabled
        assert self.event1.settings.get('payment_banktransfer_bank_details', as_type=LazyI18nString).localize('en') == "Foo"
        assert 'pretix.plugins.banktransfer' in self.event1.plugins
        with scopes_disabled():
            assert self.event1.items.count() == 2
            i = self.event1.items.first()
            assert str(i.name) == "Normal ticket"
            assert i.default_price == Decimal('13.90')
            i = self.event1.items.last()
            assert str(i.name) == "Reduced ticket"
            assert i.default_price == Decimal('13.20')
            assert self.event1.quotas.count() == 3
            q = self.event1.quotas.first()
            assert q.name == 'Normal ticket'
            assert q.size == 100
            assert q.items.count() == 1
            q = self.event1.quotas.last()
            assert q.name == 'Tickets'
            assert q.size == 120
            assert q.items.count() == 2

    def test_settings(self):
        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=date_to_0]")[0]['value'] = "2013-12-30"
        doc.select("[name=date_to_1]")[0]['value'] = "17:00:00"
        doc.select("[name=settings-max_items_per_order]")[0]['value'] = "12"

        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        assert doc.select("[name=date_to_0]")[0]['value'] == "2013-12-30"
        assert doc.select("[name=date_to_1]")[0]['value'] == "17:00:00"
        assert doc.select("[name=settings-max_items_per_order]")[0]['value'] == "12"

    def test_settings_timezone(self):
        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        doc.select("[name=date_to_0]")[0]['value'] = "2013-12-30"
        doc.select("[name=date_to_1]")[0]['value'] = "17:00:00"
        doc.select("[name=settings-max_items_per_order]")[0]['value'] = "12"
        doc.select("[name=settings-timezone]")[0]['value'] = "Asia/Tokyo"
        doc.find('option', {"value": "Asia/Tokyo"})['selected'] = 'selected'
        doc.find('option', {"value": "UTC"}).attrs.pop('selected')

        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        # date_to should not be changed even though the timezone is changed
        assert doc.select("[name=date_to_0]")[0]['value'] == "2013-12-30"
        assert doc.select("[name=date_to_1]")[0]['value'] == "17:00:00"
        assert 'selected' in doc.find('option', {"value": "Asia/Tokyo"}).attrs
        assert doc.select("[name=settings-max_items_per_order]")[0]['value'] == "12"

        self.event1.refresh_from_db()
        # Asia/Tokyo -> GMT+9
        assert self.event1.date_to.strftime('%Y-%m-%d %H:%M:%S') == "2013-12-30 08:00:00"
        assert self.event1.settings.timezone == 'Asia/Tokyo'

    def test_plugins(self):
        doc = self.get_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug))
        self.assertIn("PayPal", doc.select(".form-plugins")[0].text)
        self.assertIn("Enable", doc.select("[name=\"plugin:pretix.plugins.paypal\"]")[0].text)

        doc = self.post_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug),
                            {'plugin:pretix.plugins.paypal': 'enable'})
        self.assertIn("Disable", doc.select("[name=\"plugin:pretix.plugins.paypal\"]")[0].text)

        doc = self.post_doc('/control/event/%s/%s/settings/plugins' % (self.orga1.slug, self.event1.slug),
                            {'plugin:pretix.plugins.paypal': 'disable'})
        self.assertIn("Enable", doc.select("[name=\"plugin:pretix.plugins.paypal\"]")[0].text)

    def test_testmode_enable(self):
        self.event1.testmode = False
        self.event1.save()
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'testmode': 'true'})
        self.event1.refresh_from_db()
        assert self.event1.testmode

    def test_testmode_disable(self):
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en', testmode=True
            )
            o2 = Order.objects.create(
                code='FOO2', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            self.event1.testmode = True
            self.event1.save()
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'testmode': 'false'})
        self.event1.refresh_from_db()
        assert not self.event1.testmode
        with scopes_disabled():
            assert Order.objects.filter(pk=o.pk).exists()
            assert Order.objects.filter(pk=o2.pk).exists()

    def test_testmode_disable_delete(self):
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en', testmode=True
            )
            o2 = Order.objects.create(
                code='FOO2', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            self.event1.testmode = True
            self.event1.save()
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'testmode': 'false', 'delete': 'yes'})
        self.event1.refresh_from_db()
        assert not self.event1.testmode
        with scopes_disabled():
            assert not Order.objects.filter(pk=o.pk).exists()
            assert Order.objects.filter(pk=o2.pk).exists()

    def test_live_disable(self):
        self.event1.live = True
        self.event1.save()
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'live': 'false'})
        self.event1.refresh_from_db()
        assert not self.event1.live

    def test_live_ok(self):
        with scopes_disabled():
            self.event1.items.create(name='Test', default_price=5)
            self.event1.settings.set('payment_banktransfer__enabled', True)
            self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select("input[name=live]"))
        self.post_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug),
                      {'live': 'true'})
        self.event1.refresh_from_db()
        assert self.event1.live

    def test_live_dont_require_payment_method_free(self):
        with scopes_disabled():
            self.event1.items.create(name='Test', default_price=0)
            self.event1.settings.set('payment_banktransfer__enabled', False)
            self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select("input[name=live]"))

    def test_live_require_payment_method(self):
        with scopes_disabled():
            self.event1.items.create(name='Test', default_price=5)
            self.event1.settings.set('payment_banktransfer__enabled', False)
            self.event1.quotas.create(name='Test quota')
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select("input[name=live]")) == 0

    def test_live_require_a_quota(self):
        self.event1.settings.set('payment_banktransfer__enabled', True)
        doc = self.get_doc('/control/event/%s/%s/live/' % (self.orga1.slug, self.event1.slug))
        assert len(doc.select("input[name=live]")) == 0

    def test_payment_settings_provider(self):
        self.get_doc('/control/event/%s/%s/settings/payment/banktransfer' % (self.orga1.slug, self.event1.slug))
        self.post_doc('/control/event/%s/%s/settings/payment/banktransfer' % (self.orga1.slug, self.event1.slug), {
            'payment_banktransfer__enabled': 'true',
            'payment_banktransfer_ack': 'true',
            'payment_banktransfer__fee_abs': '12.23',
            'payment_banktransfer_bank_details_type': 'other',
            'payment_banktransfer_bank_details_0': 'Test',
            'payment_banktransfer__restrict_to_sales_channels': ['web'],
        })
        self.event1.settings.flush()
        assert self.event1.settings.get('payment_banktransfer__enabled', as_type=bool)
        assert self.event1.settings.get('payment_banktransfer__fee_abs', as_type=Decimal) == Decimal('12.23')

    def test_payment_settings(self):
        tr19 = self.event1.tax_rules.create(rate=Decimal('19.00'))
        self.get_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug))
        self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_term_days': '2',
            'payment_term_minutes': '30',
            'payment_term_mode': 'days',
            'tax_rate_default': tr19.pk,
        })
        self.event1.settings.flush()
        assert self.event1.settings.get('payment_term_days', as_type=int) == 2

    def test_payment_settings_last_date_payment_after_presale_end(self):
        tr19 = self.event1.tax_rules.create(rate=Decimal('19.00'))
        self.event1.presale_end = now()
        self.event1.save(update_fields=['presale_end'])
        doc = self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_term_days': '2',
            'payment_term_last_0': 'absolute',
            'payment_term_last_1': (self.event1.presale_end - datetime.timedelta(1)).strftime('%Y-%m-%d'),
            'payment_term_last_2': '0',
            'payment_term_last_3': 'date_from',
            'tax_rate_default': tr19.pk,
        })
        assert doc.select('.alert-danger')
        self.event1.presale_end = None
        self.event1.save(update_fields=['presale_end'])

    def test_payment_settings_relative_date_payment_after_presale_end(self):
        with scopes_disabled():
            tr19 = self.event1.tax_rules.create(rate=Decimal('19.00'))
        self.event1.presale_end = self.event1.date_from - datetime.timedelta(days=5)
        self.event1.save(update_fields=['presale_end'])
        doc = self.post_doc('/control/event/%s/%s/settings/payment' % (self.orga1.slug, self.event1.slug), {
            'payment_term_days': '2',
            'payment_term_last_0': 'relative',
            'payment_term_last_1': '',
            'payment_term_last_2': '10',
            'payment_term_last_3': 'date_from',
            'tax_rate_default': tr19.pk,
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
        self.event1.settings.flush()
        assert self.event1.settings.get('invoice_address_required', as_type=bool)

    def test_display_settings(self):
        with mocker_context() as mocker:
            mocked = mocker.patch('pretix.presale.style.regenerate_css.apply_async')

            doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
            data = extract_form_fields(doc.select("form")[0])
            data['settings-primary_color'] = '#000000'
            doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                                data, follow=True)
            assert doc.select('.alert-success')
            self.event1.settings.flush()
            assert self.event1.settings.get('primary_color') == '#000000'
            mocked.assert_any_call(args=(self.event1.pk,))

    def test_display_settings_do_not_override_parent(self):
        self.orga1.settings.primary_color = '#000000'
        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        data = extract_form_fields(doc.select("form")[0])
        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            data, follow=True)
        assert doc.select('.alert-success')
        self.event1.settings.flush()
        assert 'primary_color' not in self.event1.settings._cache()
        assert self.event1.settings.primary_color == self.orga1.settings.primary_color

    def test_display_settings_explicitly_override_parent(self):
        self.orga1.settings.primary_color = '#000000'

        doc = self.get_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug))
        data = extract_form_fields(doc.select("form")[0])
        data['decouple'] = 'primary_color'
        doc = self.post_doc('/control/event/%s/%s/settings/' % (self.orga1.slug, self.event1.slug),
                            data, follow=True)
        assert doc.select('.alert-success')
        self.event1.settings.flush()
        assert 'primary_color' in self.event1.settings._cache()
        assert self.event1.settings.primary_color == self.orga1.settings.primary_color

    def test_email_settings(self):
        with mocker_context() as mocker:
            mocked = mocker.patch('pretix.base.email.CustomSMTPBackend.test')

            doc = self.get_doc('/control/event/%s/%s/settings/email' % (self.orga1.slug, self.event1.slug))
            data = extract_form_fields(doc.select("form")[0])
            data['test'] = '1'
            doc = self.post_doc('/control/event/%s/%s/settings/email' % (self.orga1.slug, self.event1.slug),
                                data, follow=True)
            print(doc)
            assert doc.select('.alert-success')
            self.event1.settings.flush()
            assert mocked.called

    def test_ticket_settings(self):
        doc = self.get_doc('/control/event/%s/%s/settings/tickets' % (self.orga1.slug, self.event1.slug))
        data = extract_form_fields(doc.select("form")[0])
        data['ticket_download'] = 'on'
        data['ticketoutput_testdummy__enabled'] = 'on'
        doc = self.post_doc('/control/event/%s/%s/settings/tickets' % (self.orga1.slug, self.event1.slug),
                            data, follow=True)
        self.event1.settings.flush()
        assert self.event1.settings.get('ticket_download', as_type=bool)

    def test_create_event_unauthorized(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga2.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select(".has-error")

    def test_create_invalid_default_language(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('de',)
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from': '2016-12-27 10:00:00',
            'basics-date_to': '2016-12-30 19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start': '2016-11-01 10:00:00',
            'basics-presale_end': '2016-11-30 18:00:00',
        })
        assert doc.select(".has-error")

    def test_create_duplicate_slug(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-prefix': 'event_wizard',
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('de', 'en')
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '31c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
        })
        assert doc.select(".has-error")

    def test_create_event_success(self):
        doc = self.get_doc('/control/events/add')

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select("#id_basics-name_0")
        assert doc.select("#id_basics-name_1")

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '19.00',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
            'basics-team': '',
        })

        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': ''
        })

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.name == LazyI18nString({'de': '33C3', 'en': '33C3'})
            assert ev.settings.locales == ['en', 'de']
            assert ev.settings.locale == 'en'
            assert ev.currency == 'EUR'
            assert ev.settings.timezone == 'Europe/Berlin'
            assert ev.organizer == self.orga1
            assert ev.location == LazyI18nString({'de': 'Hamburg', 'en': 'Hamburg'})
            assert Team.objects.filter(limit_events=ev, members=self.user).exists()

            berlin_tz = timezone('Europe/Berlin')
            assert ev.date_from == berlin_tz.localize(datetime.datetime(2016, 12, 27, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.date_to == berlin_tz.localize(datetime.datetime(2016, 12, 30, 19, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_start == berlin_tz.localize(datetime.datetime(2016, 11, 1, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_end == berlin_tz.localize(datetime.datetime(2016, 11, 30, 18, 0, 0)).astimezone(pytz.utc)

            assert ev.tax_rules.filter(rate=Decimal('19.00')).exists()

    def test_create_event_with_subevents_success(self):
        doc = self.get_doc('/control/events/add')
        tabletext = doc.select("form")[0].text
        self.assertIn("CCC", tabletext)
        self.assertNotIn("MRM", tabletext)

        doc = self.post_doc('/control/events/add', {
            'event_wizard-prefix': 'event_wizard',
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en', 'de'),
            'foundation-has_subevents': 'on',
        })
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
            'basics-team': '',
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': ''
        })
        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.has_subevents
            assert ev.subevents.count() == 0

    def test_create_event_copy_success(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(
                rate=19, name="VAT"
            )
            q1 = self.event1.quotas.create(
                name='Foo',
                size=0,
            )
            self.event1.items.create(
                name='Early-bird ticket',
                category=None, default_price=23, tax_rule=tr,
                admission=True, hidden_if_available=q1
            )
            self.event1.settings.tax_rate_default = tr
        doc = self.get_doc('/control/events/add')

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select("#id_basics-name_0")
        assert doc.select("#id_basics-name_1")

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '19.00',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
        })

        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': self.event1.pk
        })

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.name == LazyI18nString({'de': '33C3', 'en': '33C3'})
            assert ev.settings.locales == ['en', 'de']
            assert ev.settings.locale == 'en'
            assert ev.currency == 'EUR'
            assert ev.settings.timezone == 'Europe/Berlin'
            assert ev.organizer == self.orga1
            assert ev.location == LazyI18nString({'de': 'Hamburg', 'en': 'Hamburg'})
            assert Team.objects.filter(limit_events=ev, members=self.user).exists()
            assert ev.items.count() == 1

            berlin_tz = timezone('Europe/Berlin')
            assert ev.date_from == berlin_tz.localize(datetime.datetime(2016, 12, 27, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.date_to == berlin_tz.localize(datetime.datetime(2016, 12, 30, 19, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_start == berlin_tz.localize(datetime.datetime(2016, 11, 1, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_end == berlin_tz.localize(datetime.datetime(2016, 11, 30, 18, 0, 0)).astimezone(pytz.utc)

            assert ev.tax_rules.filter(rate=Decimal('19.00')).count() == 1
            i = ev.items.get()
            assert i.hidden_if_available.name == "Foo"
            assert i.hidden_if_available.event == ev
            assert i.hidden_if_available.pk != q1.pk

    def test_create_event_clone_success(self):
        with scopes_disabled():
            tr = self.event1.tax_rules.create(
                rate=19, name="VAT"
            )
            self.event1.items.create(
                name='Early-bird ticket',
                category=None, default_price=23, tax_rule=tr,
                admission=True
            )
        self.event1.settings.tax_rate_default = tr
        doc = self.get_doc('/control/events/add?clone=' + str(self.event1.pk))
        tabletext = doc.select("form")[0].text
        self.assertIn("CCC", tabletext)
        self.assertNotIn("MRM", tabletext)

        doc = self.post_doc('/control/events/add?clone=' + str(self.event1.pk), {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en', 'de')
        })
        assert doc.select("#id_basics-date_from_0")[0]['value'] == '2013-12-26'

        doc = self.post_doc('/control/events/add?clone=' + str(self.event1.pk), {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-name_1': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-location_1': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '19.00',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
            'basics-team': '',
        })

        assert not doc.select("#id_copy-copy_from_event_1")

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.name == LazyI18nString({'de': '33C3', 'en': '33C3'})
            assert ev.settings.locales == ['en', 'de']
            assert ev.settings.locale == 'en'
            assert ev.currency == 'EUR'
            assert ev.settings.timezone == 'Europe/Berlin'
            assert ev.organizer == self.orga1
            assert ev.location == LazyI18nString({'de': 'Hamburg', 'en': 'Hamburg'})
            assert Team.objects.filter(limit_events=ev, members=self.user).exists()
            assert ev.items.count() == 1

            berlin_tz = timezone('Europe/Berlin')
            assert ev.date_from == berlin_tz.localize(datetime.datetime(2016, 12, 27, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.date_to == berlin_tz.localize(datetime.datetime(2016, 12, 30, 19, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_start == berlin_tz.localize(datetime.datetime(2016, 11, 1, 10, 0, 0)).astimezone(pytz.utc)
            assert ev.presale_end == berlin_tz.localize(datetime.datetime(2016, 11, 30, 18, 0, 0)).astimezone(pytz.utc)

            assert ev.tax_rules.filter(rate=Decimal('19.00')).count() == 1

    def test_create_event_only_date_from(self):
        # date_to, presale_start & presale_end are optional fields
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '',
            'basics-date_to_1': '',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'UTC',
            'basics-presale_start_0': '',
            'basics-presale_start_1': '',
            'basics-presale_end_0': '',
            'basics-presale_end_1': '',
            'basics-team': '',
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': ''
        })

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.name == LazyI18nString({'en': '33C3'})
            assert ev.settings.locales == ['en']
            assert ev.settings.locale == 'en'
            assert ev.currency == 'EUR'
            assert ev.settings.timezone == 'UTC'
            assert ev.organizer == self.orga1
            assert ev.location == LazyI18nString({'en': 'Hamburg'})
            assert Team.objects.filter(limit_events=ev, members=self.user).exists()
            assert ev.date_from == datetime.datetime(2016, 12, 27, 10, 0, 0, tzinfo=pytz.utc)
            assert ev.date_to is None
            assert ev.presale_start is None
            assert ev.presale_end is None

    def test_create_event_existing_team(self):
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '',
            'basics-date_to_1': '',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'UTC',
            'basics-presale_start_0': '',
            'basics-presale_start_1': '',
            'basics-presale_end_0': '',
            'basics-presale_end_1': '',
            'basics-team': str(self.team2.pk),
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'event_wizard-prefix': 'event_wizard',
            'copy-copy_from_event': ''
        })

        with scopes_disabled():
            ev = Event.objects.get(slug='33c3')
            assert ev.name == LazyI18nString({'en': '33C3'})
            assert ev.settings.locales == ['en']
            assert ev.settings.locale == 'en'
            assert ev.currency == 'EUR'
            assert ev.settings.timezone == 'UTC'
            assert ev.organizer == self.orga1
            assert ev.location == LazyI18nString({'en': 'Hamburg'})
            team = Team.objects.filter(limit_events=ev, members=self.user).first()
            assert team == self.team2
            assert ev.date_from == datetime.datetime(2016, 12, 27, 10, 0, 0, tzinfo=pytz.utc)
            assert ev.date_to is None
            assert ev.presale_start is None
            assert ev.presale_end is None

    def test_create_event_missing_date_from(self):
        # date_from is mandatory
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '',
            'basics-date_from_1': '',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
        })
        assert doc.select(".has-error")

    def test_create_event_currency_symbol(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '31c4',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': '$',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
        })
        assert doc.select(".has-error")

    def test_create_event_non_iso_currency(self):
        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'event_wizard-prefix': 'event_wizard',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': 'en'
        })

        doc = self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'event_wizard-prefix': 'event_wizard',
            'basics-name_0': '33C3',
            'basics-slug': '31c5',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'ASD',
            'basics-tax_rate': '',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
            'basics-presale_start_0': '2016-11-01',
            'basics-presale_start_1': '10:00:00',
            'basics-presale_end_0': '2016-11-30',
            'basics-presale_end_1': '18:00:00',
        })
        assert doc.select(".has-error")


class SubEventsTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy',
            has_subevents=True
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.ticket = self.event1.items.create(name='Early-bird ticket',
                                               category=None, default_price=23,
                                               admission=True)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.subevent1 = self.event1.subevents.create(name='SE1', date_from=now())
        self.subevent2 = self.event1.subevents.create(name='SE2', date_from=now())

    def test_list(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("SE1", tabletext)

    def test_create(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/add')
        assert doc.select("input[name=quotas-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/add', {
            'name_0': 'SE2',
            'active': 'on',
            'date_from_0': '2017-07-01',
            'date_from_1': '10:00:00',
            'date_to_0': '2017-07-01',
            'date_to_1': '12:00:00',
            'location_0': 'Hamburg',
            'presale_start_0': '2017-06-20',
            'presale_start_1': '10:00:00',
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-name': 'Default',
            'checkinlist_set-0-all_products': 'on',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'item-%d-price' % self.ticket.pk: '12'
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            se = self.event1.subevents.first()
            assert str(se.name) == "SE2"
            assert se.active
            assert se.date_from.isoformat() == "2017-07-01T10:00:00+00:00"
            assert se.date_to.isoformat() == "2017-07-01T12:00:00+00:00"
            assert str(se.location) == "Hamburg"
            assert se.presale_start.isoformat() == "2017-06-20T10:00:00+00:00"
            assert not se.presale_end
            assert se.quotas.count() == 1
            q = se.quotas.last()
            assert q.name == "Q1"
            assert q.size == 50
            assert list(q.items.all()) == [self.ticket]
            sei = SubEventItem.objects.get(subevent=se, item=self.ticket)
            assert sei.price == 12
            assert se.checkinlist_set.count() == 1

    def test_modify(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/' % self.subevent1.pk)
        assert doc.select("input[name=quotas-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/' % self.subevent1.pk, {
            'name_0': 'SE2',
            'active': 'on',
            'date_from_0': '2017-07-01',
            'date_from_1': '10:00:00',
            'date_to_0': '2017-07-01',
            'date_to_1': '12:00:00',
            'location_0': 'Hamburg',
            'presale_start_0': '2017-06-20',
            'presale_start_1': '10:00:00',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-name': 'Default',
            'checkinlist_set-0-all_products': 'on',
            'item-%d-price' % self.ticket.pk: '12'
        })
        assert doc.select(".alert-success")
        self.subevent1.refresh_from_db()
        se = self.subevent1
        assert str(se.name) == "SE2"
        assert se.active
        assert se.date_from.isoformat() == "2017-07-01T10:00:00+00:00"
        assert se.date_to.isoformat() == "2017-07-01T12:00:00+00:00"
        assert str(se.location) == "Hamburg"
        assert se.presale_start.isoformat() == "2017-06-20T10:00:00+00:00"
        assert not se.presale_end
        with scopes_disabled():
            assert se.quotas.count() == 1
            q = se.quotas.last()
            assert q.name == "Q1"
            assert q.size == 50
            assert list(q.items.all()) == [self.ticket]
            sei = SubEventItem.objects.get(subevent=se, item=self.ticket)
            assert sei.price == 12
            assert se.checkinlist_set.count() == 1

    def test_delete(self):
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk)
        assert doc.select("button")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, {})
        assert doc.select(".alert-success")
        # deleting the second event
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent2.pk, {})
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not SubEvent.objects.filter(pk=self.subevent2.pk).exists()
            assert not SubEvent.objects.filter(pk=self.subevent1.pk).exists()

    def test_delete_with_orders(self):
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            OrderPosition.objects.create(
                order=o,
                item=self.ticket,
                subevent=self.subevent1,
                price=Decimal("14"),
            )
        doc = self.get_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, follow=True)
        assert doc.select(".alert-danger")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/%d/delete' % self.subevent1.pk, {}, follow=True)
        assert doc.select(".alert-danger")
        with scopes_disabled():
            assert self.event1.subevents.filter(pk=self.subevent1.pk).exists()

    def test_create_bulk(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'yearly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'count',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'location_0': 'Loc',
            'time_admission': '',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-id': '',
            'quotas-0-name': 'Bar',
            'quotas-0-size': '12',
            'quotas-0-itemvars': str(self.ticket.pk),
            'item-%d-price' % self.ticket.pk: '16',
            'checkinlist_set-TOTAL_FORMS': '1',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
            'checkinlist_set-0-id': '',
            'checkinlist_set-0-name': 'Foo',
            'checkinlist_set-0-limit_products': str(self.ticket.pk),
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 10

        assert str(ses[0].name) == "Foo"
        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[0].date_to.isoformat() == "2018-04-03T13:29:31+00:00"
        assert not ses[0].presale_start
        assert ses[0].presale_end.isoformat() == "2018-04-02T11:29:31+00:00"
        with scopes_disabled():
            assert ses[0].quotas.count() == 1
            assert list(ses[0].quotas.first().items.all()) == [self.ticket]
            assert SubEventItem.objects.get(subevent=ses[0], item=self.ticket).price == 16
            assert ses[0].checkinlist_set.count() == 1

        assert str(ses[1].name) == "Foo"
        assert ses[1].date_from.isoformat() == "2019-04-03T11:29:31+00:00"
        assert ses[1].date_to.isoformat() == "2019-04-03T13:29:31+00:00"
        assert not ses[1].presale_start
        assert ses[1].presale_end.isoformat() == "2019-04-02T11:29:31+00:00"
        with scopes_disabled():
            assert ses[1].quotas.count() == 1
            assert list(ses[1].quotas.first().items.all()) == [self.ticket]
            assert SubEventItem.objects.get(subevent=ses[0], item=self.ticket).price == 16
            assert ses[1].checkinlist_set.count() == 1

        assert ses[-1].date_from.isoformat() == "2027-04-03T11:29:31+00:00"

    def test_create_bulk_daily_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '2',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '1',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 183

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[110].date_from.isoformat() == "2018-11-09T12:29:31+00:00"  # DST :)
        assert ses[-1].date_from.isoformat() == "2019-04-02T11:29:31+00:00"

    def test_create_bulk_daily_interval_multiple_times(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '2',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '2',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'timeformset-1-time_from': '15:29:31',
            'timeformset-1-time_to': '17:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 183 * 2

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-04-03T13:29:31+00:00"
        assert ses[220].date_from.isoformat() == "2018-11-09T12:29:31+00:00"  # DST :)
        assert ses[-1].date_from.isoformat() == "2019-04-02T13:29:31+00:00"

    def test_create_bulk_exclude(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.get_doc('/control/event/ccc/30c3/subevents/bulk_add')
        assert doc.select("input[name=rruleformset-TOTAL_FORMS]")
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '2',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'daily',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '1',
            'rruleformset-0-monthly_byweekday': 'MO',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'rruleformset-1-interval': '1',
            'rruleformset-1-freq': 'weekly',
            'rruleformset-1-dtstart': '2018-04-03',
            'rruleformset-1-yearly_same': 'on',
            'rruleformset-1-yearly_bysetpos': '1',
            'rruleformset-1-yearly_byweekday': 'MO',
            'rruleformset-1-yearly_bymonth': '1',
            'rruleformset-1-monthly_same': 'on',
            'rruleformset-1-monthly_bysetpos': '1',
            'rruleformset-1-monthly_byweekday': 'MO',
            'rruleformset-1-weekly_byweekday': 'MO',
            'rruleformset-1-end': 'until',
            'rruleformset-1-count': '10',
            'rruleformset-1-until': '2019-04-03',
            'rruleformset-1-exclude': 'on',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_1': '',
            'rel_presale_end_0': 'relative',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 314

        assert ses[0].date_from.isoformat() == "2018-04-03T11:29:31+00:00"
        assert ses[5].date_from.isoformat() == "2018-04-08T11:29:31+00:00"
        assert ses[6].date_from.isoformat() == "2018-04-10T11:29:31+00:00"

    def test_create_bulk_monthly_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'monthly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'off',
            'rruleformset-0-monthly_bysetpos': '-1',
            'rruleformset-0-monthly_byweekday': 'MO,TU,WE,TH,FR',
            'rruleformset-0-weekly_byweekday': 'TH',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_0': 'unset',
            'rel_presale_end_1': '',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 12

        assert ses[0].date_from.isoformat() == "2018-04-30T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-05-31T11:29:31+00:00"
        assert ses[-1].date_from.isoformat() == "2019-03-29T12:29:31+00:00"

    def test_create_bulk_weekly_interval(self):
        with scopes_disabled():
            self.event1.subevents.all().delete()
        self.event1.settings.timezone = 'Europe/Berlin'

        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_add', {
            'rruleformset-TOTAL_FORMS': '1',
            'rruleformset-INITIAL_FORMS': '0',
            'rruleformset-MIN_NUM_FORMS': '0',
            'rruleformset-MAX_NUM_FORMS': '1000',
            'rruleformset-0-interval': '1',
            'rruleformset-0-freq': 'weekly',
            'rruleformset-0-dtstart': '2018-04-03',
            'rruleformset-0-yearly_same': 'on',
            'rruleformset-0-yearly_bysetpos': '1',
            'rruleformset-0-yearly_byweekday': 'MO',
            'rruleformset-0-yearly_bymonth': '1',
            'rruleformset-0-monthly_same': 'on',
            'rruleformset-0-monthly_bysetpos': '-1',
            'rruleformset-0-monthly_byweekday': 'MO,TU,WE,TH,FR',
            'rruleformset-0-weekly_byweekday': 'TH',
            'rruleformset-0-end': 'until',
            'rruleformset-0-count': '10',
            'rruleformset-0-until': '2019-04-03',
            'timeformset-TOTAL_FORMS': '1',
            'timeformset-INITIAL_FORMS': '0',
            'timeformset-MIN_NUM_FORMS': '1',
            'timeformset-MAX_NUM_FORMS': '1000',
            'timeformset-0-time_from': '13:29:31',
            'timeformset-0-time_to': '15:29:31',
            'name_0': 'Foo',
            'active': 'on',
            'frontpage_text_0': '',
            'rel_presale_start_0': 'unset',
            'rel_presale_start_1': '',
            'rel_presale_start_2': '1',
            'rel_presale_start_3': 'date_from',
            'rel_presale_start_4': '',
            'rel_presale_end_0': 'unset',
            'rel_presale_end_1': '',
            'rel_presale_end_2': '1',
            'rel_presale_end_3': 'date_from',
            'rel_presale_end_4': '13:29:31',
            'quotas-TOTAL_FORMS': '1',
            'quotas-INITIAL_FORMS': '0',
            'quotas-MIN_NUM_FORMS': '0',
            'quotas-MAX_NUM_FORMS': '1000',
            'quotas-0-name': 'Q1',
            'quotas-0-size': '50',
            'quotas-0-itemvars': str(self.ticket.pk),
            'checkinlist_set-TOTAL_FORMS': '0',
            'checkinlist_set-INITIAL_FORMS': '0',
            'checkinlist_set-MIN_NUM_FORMS': '0',
            'checkinlist_set-MAX_NUM_FORMS': '1000',
        })
        assert doc.select(".alert-success")
        with scopes_disabled():
            ses = list(self.event1.subevents.order_by('date_from'))
        assert len(ses) == 52

        assert ses[0].date_from.isoformat() == "2018-04-05T11:29:31+00:00"
        assert ses[1].date_from.isoformat() == "2018-04-12T11:29:31+00:00"
        assert ses[-1].date_from.isoformat() == "2019-03-28T12:29:31+00:00"

    def test_delete_bulk(self):
        self.subevent2.active = True
        self.subevent2.save()
        with scopes_disabled():
            o = Order.objects.create(
                code='FOO', event=self.event1, email='dummy@dummy.test',
                status=Order.STATUS_PENDING,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=14, locale='en'
            )
            OrderPosition.objects.create(
                order=o,
                item=self.ticket,
                subevent=self.subevent1,
                price=Decimal("14"),
            )
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': [str(self.subevent1.pk), str(self.subevent2.pk)],
            'action': 'delete_confirm'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not self.event1.subevents.filter(pk=self.subevent2.pk).exists()
            assert self.event1.subevents.get(pk=self.subevent1.pk).active is False

    def test_disable_bulk(self):
        self.subevent2.active = True
        self.subevent2.save()
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': str(self.subevent2.pk),
            'action': 'disable'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.subevents.get(pk=self.subevent2.pk).active is False

    def test_enable_bulk(self):
        self.subevent2.active = False
        self.subevent2.save()
        doc = self.post_doc('/control/event/ccc/30c3/subevents/bulk_action', {
            'subevent': str(self.subevent2.pk),
            'action': 'enable'
        }, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert self.event1.subevents.get(pk=self.subevent2.pk).active is True


class EventDeletionTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy',
            has_subevents=False
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.ticket = self.event1.items.create(name='Early-bird ticket',
                                               category=None, default_price=23,
                                               admission=True)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_delete_allowed(self):
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time())
        session.save()
        self.client.post('/control/event/ccc/30c3/delete/', {
            'slug': '30c3'
        })

        with scopes_disabled():
            assert not self.orga1.events.exists()

    def test_delete_wrong_slug(self):
        self.post_doc('/control/event/ccc/30c3/delete/', {
            'user_pw': 'dummy',
            'slug': '31c3'
        })
        with scopes_disabled():
            assert self.orga1.events.exists()

    def test_delete_wrong_pw(self):
        self.post_doc('/control/event/ccc/30c3/delete/', {
            'user_pw': 'invalid',
            'slug': '30c3'
        })
        with scopes_disabled():
            assert self.orga1.events.exists()

    def test_delete_orders(self):
        Order.objects.create(
            code='FOO', event=self.event1, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now(),
            total=14, locale='en'
        )
        self.post_doc('/control/event/ccc/30c3/delete/', {
            'user_pw': 'dummy',
            'slug': '30c3'
        })
        with scopes_disabled():
            assert self.orga1.events.exists()
