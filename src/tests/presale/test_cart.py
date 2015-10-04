import datetime
import time
from datetime import timedelta

from bs4 import BeautifulSoup
from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now
from tests.base import BrowserTest

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, ItemVariation, Organizer,
    Property, PropertyValue, Question, QuestionAnswer, Quota, User,
)


class CartTestMixin:
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc)
        )
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12)
        prop1 = Property.objects.create(event=self.event, name="Color")
        self.shirt.properties.add(prop1)
        val1 = PropertyValue.objects.create(prop=prop1, value="Red", position=0)
        val2 = PropertyValue.objects.create(prop=prop1, value="Black", position=1)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14)
        self.shirt_red.values.add(val1)
        var2 = ItemVariation.objects.create(item=self.shirt)
        var2.values.add(val2)
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(var2)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23)
        self.quota_tickets.items.add(self.ticket)

        self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.session_key = self.client.cookies.get(settings.SESSION_COOKIE_NAME).value


class CartTest(CartTestMixin, TestCase):
    def test_simple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_variation(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_' + self.shirt.identity + '_' + self.shirt_red.identity: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 14)

    def test_count(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('2', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('46', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 2)
        for obj in objs:
            self.assertEqual(obj.item, self.ticket)
            self.assertIsNone(obj.variation)
            self.assertEqual(obj.price, 23)

    def test_multiple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '2',
            'variation_' + self.shirt.identity + '_' + self.shirt_red.identity: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('Early-bird', doc.select('.cart')[0].text)
        self.assertIn('Shirt', doc.select('.cart')[0].text)
        objs = list(CartPosition.objects.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 3)
        self.assertIn(self.shirt, [obj.item for obj in objs])
        self.assertIn(self.shirt_red, [obj.variation for obj in objs])
        self.assertIn(self.ticket, [obj.item for obj in objs])

    def test_fuzzy_input(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: 'a',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('did not select any products', doc.select('.alert-warning')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

    def test_wrong_event(self):
        event2 = Event.objects.create(
            organizer=self.orga, name='MRMCD', slug='mrmcd',
            date_from=datetime.datetime(2014, 9, 6, tzinfo=datetime.timezone.utc)
        )
        shirt2 = Item.objects.create(event=event2, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + shirt2.identity: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('not available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

    def test_no_quota(self):
        shirt2 = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + shirt2.identity: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

    def test_max_items(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self.event.settings.max_items_per_order = 5
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '5',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('more than', doc.select('.alert-danger')[0].text)
        self.assertEqual(CartPosition.objects.filter(session=self.session_key, event=self.event).count(), 1)

    def test_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

    def test_quota_partly(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_renew_in_time(self):
        cp = CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
        }, follow=True)
        cp = CartPosition.objects.current.get(identity=cp.identity)
        self.assertGreater(cp.expires, now())

    def test_renew_expired_successfully(self):
        cp1 = CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%s_%s' % (self.shirt.identity, self.shirt_red.identity): '1'
        }, follow=True)
        obj = CartPosition.objects.current.get(identity=cp1.identity)
        self.assertEqual(obj.item, self.ticket)
        self.assertIsNone(obj.variation)
        self.assertEqual(obj.price, 23)
        self.assertGreater(obj.expires, now())

    def test_renew_questions(self):
        cr1 = CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        q1 = Question.objects.create(
            event=self.event, question='Age', type=Question.TYPE_NUMBER,
            required=True
        )
        self.ticket.questions.add(q1)
        cr1.answers.add(QuestionAnswer.objects.create(
            cartposition=cr1, question=q1, answer='23'
        ))
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        obj = CartPosition.objects.current.get(identity=cr1.identity)
        self.assertEqual(obj.answers.get(question=q1).answer, '23')

    def test_renew_expired_failed(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        cp1 = CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.current.filter(identity=cp1.identity).exists())

    def test_restriction_ok(self):
        self.event.plugins = 'tests.testdummy'
        self.event.save()
        self.event.settings.testdummy_available = 'yes'
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        objs = list(CartPosition.objects.current.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_restriction_failed(self):
        self.event.plugins = 'tests.testdummy'
        self.event.save()
        self.event.settings.testdummy_available = 'no'
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(session=self.session_key, event=self.event).exists())

    def test_remove_simple(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.current.filter(session=self.session_key, event=self.event).exists())

    def test_remove_variation(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.shirt, variation=self.shirt_red,
            price=14, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'variation_' + self.shirt.identity + '_' + self.shirt_red.identity: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.current.filter(session=self.session_key, event=self.event).exists())

    def test_remove_one_of_multiple(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertEqual(CartPosition.objects.current.filter(session=self.session_key, event=self.event).count(), 1)

    def test_remove_multiple(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '2',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.current.filter(session=self.session_key, event=self.event).exists())

    def test_remove_most_expensive(self):
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, session=self.session_key, item=self.ticket,
            price=20, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_' + self.ticket.identity: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content)
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        objs = list(CartPosition.objects.current.filter(session=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 20)
