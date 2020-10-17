import datetime
import decimal
import json

from django.core import mail as djmail
from django.test import TransactionTestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTestMixin, extract_form_fields

from pretix.base.models import (
    Event, Item, ItemVariation, Order, OrderPosition, Organizer, Quota, Team,
    User, Voucher,
)


class VoucherFormTest(SoupTestMixin, TransactionTestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga, can_view_vouchers=True, can_change_vouchers=True)
        t.members.add(self.user)
        t.limit_events.add(self.event)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value='Red')
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value='Blue')
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          default_price=23)
        self.quota_tickets.items.add(self.ticket)

    def _create_voucher(self, data, expected_failure=False):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            if expected_failure:
                assert doc.select(".alert-danger, .has-error")
                assert count_before == self.event.vouchers.count()
            else:
                assert doc.select(".alert-success")
                assert count_before + 1 == self.event.vouchers.count()

    def _create_bulk_vouchers(self, data, expected_failure=False):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/bulk_add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/bulk_add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            if expected_failure:
                assert doc.select(".alert-danger")
                assert count_before == self.event.vouchers.count()
            else:
                assert doc.select(".alert-success")
                assert count_before + len(form_data.get('codes').split("\n")) == self.event.vouchers.count()

    def _change_voucher(self, v, data, expected_failure=False):
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, v.pk))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update(data)
        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, v.pk), form_data)
        if expected_failure:
            assert doc.select(".alert-danger")
        else:
            assert doc.select(".alert-success")

    def test_list(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG')
        doc = self.client.get('/control/event/%s/%s/vouchers/' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()

    def test_csv(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG')
        doc = self.client.get('/control/event/%s/%s/vouchers/?download=yes' % (self.orga.slug, self.event.slug))
        assert doc.content.decode().strip() == '"Voucher code","Valid until","Product","Reserve quota",' \
                                               '"Bypass quota","Price effect","Value","Tag","Redeemed",' \
                                               '"Maximum usages","Seat"' \
                                               '\r\n"ABCDEFG","","Early-bird ticket","No","No","No effect","","","0",' \
                                               '"1",""'

    def test_filter_status_valid(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=v' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()
        v.redeemed = 1
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=v' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()

    def test_filter_status_redeemed(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, redeemed=1)
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=r' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()
        v.redeemed = 0
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=r' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()

    def test_filter_status_expired(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() + datetime.timedelta(days=1))
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=e' % (self.orga.slug, self.event.slug))
        assert v.code not in doc.content.decode()
        v.valid_until = now() - datetime.timedelta(days=1)
        v.save()
        doc = self.client.get('/control/event/%s/%s/vouchers/?status=e' % (self.orga.slug, self.event.slug))
        assert v.code in doc.content.decode()

    def test_filter_tag(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG', comment='Foo', tag='bar')
        doc = self.client.get('/control/event/%s/%s/vouchers/?tag=bar' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?tag=baz' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' not in doc.content.decode()

    def test_search_code(self):
        with scopes_disabled():
            self.event.vouchers.create(item=self.ticket, code='ABCDEFG', comment='Foo')
        doc = self.client.get('/control/event/%s/%s/vouchers/?search=ABCDEFG' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?search=Foo' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' in doc.content.decode()
        doc = self.client.get('/control/event/%s/%s/vouchers/?search=12345' % (self.orga.slug, self.event.slug))
        assert 'ABCDEFG' not in doc.content.decode()

    def test_bulk_rng(self):
        rng = self.client.get('/control/event/%s/%s/vouchers/rng?num=7' % (self.orga.slug, self.event.slug))
        codes = json.loads(rng.content.decode('utf-8'))['codes']
        assert len(codes) == 7
        assert all([len(r) == 16 for r in codes])

    def test_display_voucher_code(self):
        with scopes_disabled():
            count_before = self.event.vouchers.count()
        doc = self.get_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data.update({
            'itemvar': '%d' % self.ticket.pk
        })
        doc = self.post_doc('/control/event/%s/%s/vouchers/add' % (self.orga.slug, self.event.slug), form_data)
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
            assert v.code in doc.select(".alert-success")[0].text
            assert count_before + 1 == self.event.vouchers.count()

    def test_create_voucher_for_addon_item(self):
        with scopes_disabled():
            c = self.event.categories.create(name="Foo", is_addon=True)
        self.ticket.category = c
        self.ticket.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk
        }, expected_failure=True)

    def test_create_non_blocking_item_voucher(self):
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item.pk == self.ticket.pk
        assert v.variation is None
        assert v.quota is None

    def test_create_non_blocking_variation_voucher(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk)
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item.pk == self.shirt.pk
        assert v.variation.pk == self.shirt_red.pk
        assert v.quota is None

    def test_create_non_blocking_quota_voucher(self):
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert not v.block_quota
        assert v.item is None
        assert v.variation is None
        assert v.quota.pk == self.quota_tickets.pk

    def test_create_blocking_item_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_blocking_item_voucher_quota_full(self):
        self._create_voucher({
            'itemvar': '%d' % self.shirt.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_blocking_item_voucher_quota_full_invalid(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on',
            'valid_until_0': (now() - datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() - datetime.timedelta(days=3)).strftime('%H:%M:%S')
        })

    def test_create_blocking_variation_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_short_code(self):
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'code': 'ABC'
        }, expected_failure=True)

    def test_create_blocking_variation_voucher_quota_full(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        self._create_voucher({
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_red.pk),
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_blocking_quota_voucher_quota_free(self):
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
            'block_quota': 'on'
        })
        with scopes_disabled():
            v = Voucher.objects.latest('pk')
        assert v.block_quota

    def test_create_blocking_quota_voucher_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_change_non_blocking_voucher(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_tickets.pk
        })
        v.refresh_from_db()
        assert v.item is None
        assert v.variation is None
        assert v.quota.pk == self.quota_tickets.pk

    def test_change_blocking_voucher_unchanged_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
        })
        v.refresh_from_db()
        assert v.block_quota

    def test_change_voucher_reduce_max_usages(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, max_usages=5, redeemed=3)
        self._change_voucher(v, {
            'max_usages': '2'
        }, expected_failure=True)

    def test_change_voucher_to_blocking_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'block_quota': 'on'
        }, expected_failure=True)

    def test_change_voucher_to_blocking_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket)
        self._change_voucher(v, {
            'block_quota': 'on'
        })
        v.refresh_from_db()
        assert v.block_quota

    def test_change_voucher_validity_to_valid_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() - datetime.timedelta(days=3),
                                           block_quota=True)
        self._change_voucher(v, {
            'valid_until_0': (now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() + datetime.timedelta(days=3)).strftime('%H:%M:%S')
        }, expected_failure=True)
        v.refresh_from_db()
        assert v.valid_until < now()

    def test_change_voucher_validity_to_valid_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(item=self.ticket, valid_until=now() - datetime.timedelta(days=3),
                                           block_quota=True)
        self._change_voucher(v, {
            'valid_until_0': (now() + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'valid_until_1': (now() + datetime.timedelta(days=3)).strftime('%H:%M:%S')
        })
        v.refresh_from_db()
        assert v.valid_until > now()

    def test_change_item_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            ticket2 = Item.objects.create(event=self.event, name='Late-bird ticket', default_price=23)
            self.quota_tickets.items.add(ticket2)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % ticket2.pk,
        })

    def test_change_item_of_blocking_voucher_quota_full(self):
        self.quota_shirts.size = 0
        self.quota_shirts.save()
        with scopes_disabled():
            hoodie = Item.objects.create(event=self.event, name='Hoodie', default_price=23)
            self.quota_shirts.items.add(hoodie)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % hoodie.pk,
        }, expected_failure=True)

    def test_change_variation_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            self.quota_shirts.variations.remove(self.shirt_blue)
            self.quota_tickets.variations.add(self.shirt_blue)
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        })

    def test_change_variation_of_blocking_voucher_quota_full(self):
        with scopes_disabled():
            self.quota_shirts.variations.remove(self.shirt_blue)
            self.quota_tickets.variations.add(self.shirt_blue)
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        }, expected_failure=True)

    def test_change_quota_of_blocking_voucher_quota_free(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_shirts.pk,
        })

    def test_change_quota_of_blocking_voucher_quota_full(self):
        with scopes_disabled():
            self.quota_shirts.size = 0
            self.quota_shirts.save()
            v = self.event.vouchers.create(quota=self.quota_tickets, block_quota=True)
        self._change_voucher(v, {
            'itemvar': 'q-%d' % self.quota_shirts.pk,
        }, expected_failure=True)

    def test_change_item_of_blocking_voucher_without_quota_change(self):
        with scopes_disabled():
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            ticket2 = Item.objects.create(event=self.event, name='Standard Ticket', default_price=23)
            self.quota_tickets.items.add(ticket2)
            v = self.event.vouchers.create(item=self.ticket, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d' % ticket2.pk,
        })

    def test_change_variation_of_blocking_voucher_without_quota_change(self):
        with scopes_disabled():
            self.quota_shirts.size = 0
            self.quota_shirts.save()
            v = self.event.vouchers.create(item=self.shirt, variation=self.shirt_red, block_quota=True)
        self._change_voucher(v, {
            'itemvar': '%d-%d' % (self.shirt.pk, self.shirt_blue.pk),
        })

    def test_create_duplicate_code(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        self._create_voucher({
            'code': v.code,
        }, expected_failure=True)

    def test_change_code_to_duplicate(self):
        with scopes_disabled():
            v1 = self.event.vouchers.create(quota=self.quota_tickets)
            v2 = self.event.vouchers.create(quota=self.quota_tickets)
        self._change_voucher(v1, {
            'code': v2.code
        }, expected_failure=True)

    def test_create_bulk(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
        })

    def test_create_bulk_many(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH\nIJKLM\nNOPQR\nSTUVW\nXYZ',
            'itemvar': '%d' % self.ticket.pk,
        })

    def test_create_blocking_bulk_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_blocking_bulk_quota_free(self):
        self.quota_tickets.size = 5
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        })

    def test_create_blocking_bulk_quota_partial(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_create_bulk_with_duplicate_code(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        self._create_bulk_vouchers({
            'codes': 'ABCDE\n%s' % v.code,
            'itemvar': '%d' % self.shirt.pk,
        }, expected_failure=True)

    def test_create_bulk_send(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        })
        assert len(djmail.outbox) == 2
        assert len([m for m in djmail.outbox if m.to == ['foo@example.com']]) == 1
        assert len([m for m in djmail.outbox if m.to == ['foo@example.net']]) == 1
        assert len([m for m in djmail.outbox if 'ABCDE' in m.body]) == 1
        assert len([m for m in djmail.outbox if 'DEFGH' in m.body]) == 1

    def test_create_bulk_send_csv(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number\nfoo@example.com,2'
        })
        assert len(djmail.outbox) == 1
        assert 'ABCDE' in djmail.outbox[0].body
        assert 'DEFGH' in djmail.outbox[0].body
        assert ['foo@example.com'] == djmail.outbox[0].to

    def test_create_bulk_send_csv_tag(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number,tag\nfoo@example.com,2,mytag'
        })
        assert len(djmail.outbox) == 1
        assert 'ABCDE' in djmail.outbox[0].body
        assert 'DEFGH' in djmail.outbox[0].body
        assert ['foo@example.com'] == djmail.outbox[0].to
        with scopes_disabled():
            assert Voucher.objects.get(code="ABCDE").tag == "mytag"

    def test_create_bulk_send_invalid_placeholder(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {order}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        }, expected_failure=True)

    def test_create_bulk_send_empty_subject(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': '',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        }, expected_failure=True)

    def test_create_bulk_send_invalid_mail_list(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo\nfoo@example.org'
        }, expected_failure=True)

    def test_create_bulk_send_invalid_mail_count(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo@example.org'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_header(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foooo@example.org,bar,baz'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_header_email(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'mail,number,tag\nfoooo@example.org,2,baz'
        }, expected_failure=True)

    def test_create_bulk_send_missing_csv_unknown_header(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'email,number,flop\nfoooo@example.org,2,baz'
        }, expected_failure=True)

    def test_resend(self):
        self._create_bulk_vouchers({
            'codes': 'ABCDE\nDEFGH',
            'itemvar': '%d' % self.shirt.pk,
            'send': 'on',
            'send_subject': 'Your voucher',
            'send_message': 'Voucher list: {voucher_list}',
            'send_recipients': 'foo@example.com\nfoo@example.net'
        })
        assert len(djmail.outbox) == 2
        assert len([m for m in djmail.outbox if m.to == ['foo@example.com']]) == 1
        assert len([m for m in djmail.outbox if m.to == ['foo@example.net']]) == 1
        assert len([m for m in djmail.outbox if 'ABCDE' in m.body]) == 1
        assert len([m for m in djmail.outbox if 'DEFGH' in m.body]) == 1
        with scopes_disabled():
            v = self.event.vouchers.get(recipient='foo@example.com')
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/resend' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert doc.select(".alert-success")
        assert len(djmail.outbox) == 3
        assert len([m for m in djmail.outbox if m.to == ['foo@example.com']]) == 2
        assert len([m for m in djmail.outbox if m.to == ['foo@example.net']]) == 1
        assert len([m for m in djmail.outbox if 'ABCDE' in m.body]) == 1
        # codes get assigned in reverse order, so foo@example.com got 'DEFGH'
        assert len([m for m in djmail.outbox if 'DEFGH' in m.body]) == 2

    def test_resend_missing_recipient(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/resend' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert doc.select(".alert-danger")

    # TODO test bulk resend

    def test_delete_voucher(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets)
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert not doc.select(".alert-danger")

        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                            {}, follow=True)
        assert doc.select(".alert-success")
        with scopes_disabled():
            assert not self.event.vouchers.filter(pk=v.id).exists()

    def test_delete_voucher_redeemed(self):
        with scopes_disabled():
            v = self.event.vouchers.create(quota=self.quota_tickets, redeemed=1)
        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                           follow=True)
        assert doc.select(".alert-danger")

        doc = self.post_doc('/control/event/%s/%s/vouchers/%s/delete' % (self.orga.slug, self.event.slug, v.pk),
                            {}, follow=True)
        assert doc.select(".alert-danger")

    def test_subevent_optional(self):
        self.event.has_subevents = True
        self.event.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
        })

    def test_subevent_non_blocking_quota_no_date(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.save()

        self._create_voucher({
            'itemvar': 'q-%d' % self.quota_tickets.pk,
        })

    def test_subevent_required_for_blocking(self):
        self.event.has_subevents = True
        self.event.save()
        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on'
        }, expected_failure=True)

    def test_subevent_blocking_quota_free(self):
        with scopes_disabled():
            self.event.has_subevents = True
            self.event.save()
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.save()
            q2 = Quota.objects.create(event=self.event, name='Tickets', size=0, subevent=se2)
            q2.items.add(self.ticket)

        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on',
            'subevent': se1.pk
        })

    def test_subevent_blocking_quota_full(self):
        self.event.has_subevents = True
        self.event.save()
        with scopes_disabled():
            se1 = self.event.subevents.create(name="Foo", date_from=now())
            se2 = self.event.subevents.create(name="Bar", date_from=now())

            self.quota_tickets.subevent = se1
            self.quota_tickets.size = 0
            self.quota_tickets.save()
            q2 = Quota.objects.create(event=self.event, name='Tickets', size=5, subevent=se2)
            q2.items.add(self.ticket)

        self._create_voucher({
            'itemvar': '%d' % self.ticket.pk,
            'block_quota': 'on',
            'subevent': se1.pk
        }, expected_failure=True)

    def test_order_warning_deduplication(self):
        with scopes_disabled():
            shirt_voucher = Voucher.objects.create(
                event=self.event, item=self.shirt, price_mode='set', value=0.0, max_usages=100
            )

            shirt_order = Order.objects.create(
                code='DEDUP', event=self.event, email='dummy@dummy.test',
                status=Order.STATUS_PAID,
                datetime=now(), expires=now() + datetime.timedelta(days=10),
                total=0, locale='en'
            )

            OrderPosition.objects.create(
                order=shirt_order,
                item=self.shirt,
                variation=self.shirt_red,
                price=decimal.Decimal("0"),
                voucher=shirt_voucher
            )

            OrderPosition.objects.create(
                order=shirt_order,
                item=self.shirt,
                variation=self.shirt_blue,
                price=decimal.Decimal("0"),
                voucher=shirt_voucher
            )

        shirt_voucher.redeemed = 2
        shirt_voucher.save()

        doc = self.get_doc('/control/event/%s/%s/vouchers/%s/' % (self.orga.slug, self.event.slug, shirt_voucher.pk))

        assert len(doc.select('.alert-warning ul li')) == 1  # Check that there's exactly 1 item in the warning list
        assert doc.text.count('Order DEDUP') == 1  # Check that the order is listed exactly once
