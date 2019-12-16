import datetime
import json
import time
from io import BytesIO
from zipfile import ZipFile

from django.utils.timezone import now
from django_scopes import scopes_disabled
from tests.base import SoupTest

from pretix.base.models import Event, Order, Organizer, Team, User


class EventShredderTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,pretix.plugins.stripe,tests.testdummy'
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True, can_change_orders=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.order = Order.objects.create(
            code='FOO', event=self.event1, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now(),
            total=14, locale='en'
        )

        self.client.login(email='dummy@dummy.dummy', password='dummy')
        session = self.client.session
        session['pretix_auth_login_time'] = int(time.time()) * 2
        session.save()

    def test_shred_simple(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'slug': self.event1.slug
        })
        assert doc.select('.alert-success')
        self.order.refresh_from_db()
        assert not self.order.email

    def test_shred_password_wrong(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'test'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email

    def test_shred_confirm_code_wrong(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'][::-1] + 'A',
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'dummy'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email

    def test_shred_constraints(self):
        self.event1.live = True
        self.event1.save()
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert not doc.select("input[value=order_emails]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select('.alert-danger')

    def test_shred_something_happened(self):
        doc = self.get_doc('/control/event/%s/%s/shredder/' % (self.orga1.slug, self.event1.slug))
        assert doc.select("input[value=order_emails]")
        assert doc.select("input[value=invoices]")
        doc = self.post_doc('/control/event/%s/%s/shredder/export' % (self.orga1.slug, self.event1.slug), {
            'shredder': 'order_emails'
        })
        assert doc.select("a.btn-primary")[0].text.strip() == "Download data"
        dlink = doc.select("a.btn-primary")[0].attrs['href']
        zipfiler = self.client.get(dlink)
        with ZipFile(BytesIO(zipfiler.getvalue()), 'r') as zipfile:
            indexdata = json.loads(zipfile.read('index.json').decode())
            assert indexdata['shredders'] == ['order_emails']
            assert indexdata['organizer'] == 'ccc'
            assert indexdata['event'] == '30c3'
            assert zipfile.read('CONFIRM_CODE.txt').decode() == indexdata['confirm_code']

            maildata = json.loads(zipfile.read('emails-by-order.json').decode())
            assert maildata == {
                'FOO': 'dummy@dummy.test'
            }
        self.order.log_action('dummy')
        doc = self.post_doc('/control/event/%s/%s/shredder/shred' % (self.orga1.slug, self.event1.slug), {
            'confirm_code': indexdata['confirm_code'],
            'file': doc.select("input[name=file]")[0].attrs['value'],
            'password': 'dummy'
        })
        assert doc.select('.alert-danger')
        self.order.refresh_from_db()
        assert self.order.email
