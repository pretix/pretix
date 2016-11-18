import datetime
from datetime import timedelta
from decimal import Decimal

from bs4 import BeautifulSoup
from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, ItemVariation, Organizer,
    Question, QuestionAnswer, Quota, Voucher,
)


class CartTestMixin:
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            live=True
        )
        self.category = ItemCategory.objects.create(event=self.event, name="Everything", position=0)
        self.quota_shirts = Quota.objects.create(event=self.event, name='Shirts', size=2)
        self.shirt = Item.objects.create(event=self.event, name='T-Shirt', category=self.category, default_price=12)
        self.quota_shirts.items.add(self.shirt)
        self.shirt_red = ItemVariation.objects.create(item=self.shirt, default_price=14, value='Red')
        self.shirt_blue = ItemVariation.objects.create(item=self.shirt, value='Blue')
        self.quota_shirts.variations.add(self.shirt_red)
        self.quota_shirts.variations.add(self.shirt_blue)
        self.quota_tickets = Quota.objects.create(event=self.event, name='Tickets', size=5)
        self.ticket = Item.objects.create(event=self.event, name='Early-bird ticket',
                                          category=self.category, default_price=23)
        self.quota_tickets.items.add(self.ticket)

        self.client.get('/%s/%s/' % (self.orga.slug, self.event.slug))
        self.session_key = self.client.cookies.get(settings.SESSION_COOKIE_NAME).value


class CartTest(CartTestMixin, TestCase):
    def test_simple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_free_price(self):
        self.ticket.free_price = True
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '24.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('24', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('24', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 24)

    def test_free_price_only_if_allowed(self):
        self.ticket.free_price = False
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '24.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_free_price_lower_bound(self):
        self.ticket.free_price = False
        self.ticket.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
            'price_%d' % self.ticket.id: '12.00'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_variation_inactive(self):
        self.shirt_red.active = False
        self.shirt_red.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_variation(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('14', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 14)

    def test_variation_free_price(self):
        self.shirt.free_price = True
        self.shirt.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
            'price_%d_%d' % (self.shirt.id, self.shirt_red.id): '16',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Shirt', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('Red', doc.select('.cart .cart-row')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('16', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('16', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)
        self.assertEqual(objs[0].price, 16)

    def test_count(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('2', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('46', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 2)
        for obj in objs:
            self.assertEqual(obj.item, self.ticket)
            self.assertIsNone(obj.variation)
            self.assertEqual(obj.price, 23)

    def test_multiple(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('Early-bird', doc.select('.cart')[0].text)
        self.assertIn('Shirt', doc.select('.cart')[0].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 3)
        self.assertIn(self.shirt, [obj.item for obj in objs])
        self.assertIn(self.shirt_red, [obj.variation for obj in objs])
        self.assertIn(self.ticket, [obj.item for obj in objs])

    def test_fuzzy_input(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: 'a',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '-2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_blue.id): 'a',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_a_%d' % (self.shirt_blue.id): '-2',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('numbers only', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('did not select any products', doc.select('.alert-warning')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_wrong_event(self):
        event2 = Event.objects.create(
            organizer=self.orga, name='MRMCD', slug='mrmcd',
            date_from=datetime.datetime(2014, 9, 6, tzinfo=datetime.timezone.utc)
        )
        shirt2 = Item.objects.create(event=event2, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % shirt2.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('not available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_no_quota(self):
        shirt2 = Item.objects.create(event=self.event, name='T-Shirt', default_price=12)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % shirt2.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_in_time_available(self):
        self.ticket.available_until = now() + timedelta(days=2)
        self.ticket.available_from = now() - timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_no_longer_available(self):
        self.ticket.available_until = now() - timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_not_yet_available(self):
        self.ticket.available_from = now() + timedelta(days=2)
        self.ticket.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_max_items(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self.event.settings.max_items_per_order = 5
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '5',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('more than', doc.select('.alert-danger')[0].text)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_quota_full(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_quota_partly(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2'
        }, follow=True)
        self.assertRedirects(response, '/%s/%s/' % (self.orga.slug, self.event.slug),
                             target_status_code=200)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertIn('Early-bird', doc.select('.cart .cart-row')[0].select('strong')[0].text)
        self.assertIn('1', doc.select('.cart .cart-row')[0].select('.count')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[0].text)
        self.assertIn('23', doc.select('.cart .cart-row')[0].select('.price')[1].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_renew_in_time(self):
        cp = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
        }, follow=True)
        cp = CartPosition.objects.get(id=cp.id)
        self.assertGreater(cp.expires, now())

    def test_renew_expired_successfully(self):
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        obj = CartPosition.objects.get(id=cp1.id)
        self.assertEqual(obj.item, self.ticket)
        self.assertIsNone(obj.variation)
        self.assertEqual(obj.price, 23)
        self.assertGreater(obj.expires, now())

    def test_renew_questions(self):
        cr1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
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
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        obj = CartPosition.objects.get(id=cr1.id)
        self.assertEqual(obj.answers.get(question=q1).answer, '23')

    def test_renew_expired_failed(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(id=cp1.id).exists())

    def test_remove_simple(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_variation(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.shirt, variation=self.shirt_red,
            price=14, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_one_of_multiple(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 1)

    def test_remove_multiple(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_all(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.shirt, variation=self.shirt_red,
            price=14, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/removeall' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '2',
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('empty', doc.select('.alert-success')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_remove_most_expensive(self):
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() + timedelta(minutes=10)
        )
        CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=20, expires=now() + timedelta(minutes=10)
        )
        response = self.client.post('/%s/%s/cart/remove' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('updated', doc.select('.alert-success')[0].text)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 20)

    def test_voucher(self):
        v = Voucher.objects.create(item=self.ticket, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, 23)

    def test_voucher_expired_readd(self):
        v = Voucher.objects.create(item=self.ticket, event=self.event, block_quota=True)
        cp1 = CartPosition.objects.create(
            event=self.event, cart_id=self.session_key, item=self.ticket,
            price=23, expires=now() - timedelta(minutes=10), voucher=v
        )
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1'
        }, follow=True)
        obj = CartPosition.objects.get(id=cp1.id)
        self.assertGreater(obj.expires, now())

    def test_voucher_variation(self):
        v = Voucher.objects.create(item=self.shirt, variation=self.shirt_red, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_voucher_quota(self):
        v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_voucher_quota_invalid_item(self):
        v = Voucher.objects.create(quota=self.quota_tickets, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_item_invalid_item(self):
        v = Voucher.objects.create(item=self.shirt, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_item_invalid_variation(self):
        v = Voucher.objects.create(item=self.shirt, variation=self.shirt_blue, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_price(self):
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_redemed(self):
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event, redeemed=True)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already been used', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_expired(self):
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event,
                                   valid_until=now() - timedelta(days=2))
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('expired', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_invalid(self):
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: 'ABC',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('not known', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_quota_empty(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())

    def test_voucher_quota_ignore(self):
        self.quota_tickets.size = 0
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event,
                                   allow_ignore_quota=True)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_quota_block(self):
        self.quota_tickets.size = 1
        self.quota_tickets.save()
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event,
                                   block_quota=True)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d' % self.ticket.id: '1',
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('no longer available', doc.select('.alert-danger')[0].text)
        self.assertFalse(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).exists())
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

    def test_voucher_doubled(self):
        v = Voucher.objects.create(item=self.ticket, price=Decimal('12.00'), event=self.event)
        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.ticket)
        self.assertIsNone(objs[0].variation)
        self.assertEqual(objs[0].price, Decimal('12.00'))

        response = self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'item_%d_voucher' % self.ticket.id: v.code,
        }, follow=True)
        doc = BeautifulSoup(response.rendered_content, "lxml")
        self.assertIn('already used', doc.select('.alert-danger')[0].text)
        self.assertEqual(1, CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count())

    def test_require_voucher(self):
        v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.shirt.require_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_require_voucher_failed(self):
        self.shirt.require_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)

    def test_voucher_quota_other_quota_full(self):
        quota2 = self.event.quotas.create(name='Test', size=0)
        quota2.variations.add(self.shirt_red)
        v = Voucher.objects.create(quota=self.quota_shirts, event=self.event)
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        self.assertEqual(CartPosition.objects.filter(cart_id=self.session_key, event=self.event).count(), 0)

    def test_hide_without_voucher(self):
        v = Voucher.objects.create(item=self.shirt, event=self.event)
        self.shirt.hide_without_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d_voucher' % (self.shirt.id, self.shirt_red.id): v.code,
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].item, self.shirt)
        self.assertEqual(objs[0].variation, self.shirt_red)

    def test_hide_without_voucher_failed(self):
        self.shirt.hide_without_voucher = True
        self.shirt.save()
        self.client.post('/%s/%s/cart/add' % (self.orga.slug, self.event.slug), {
            'variation_%d_%d' % (self.shirt.id, self.shirt_red.id): '1',
        }, follow=True)
        objs = list(CartPosition.objects.filter(cart_id=self.session_key, event=self.event))
        self.assertEqual(len(objs), 0)
