import datetime
from decimal import Decimal

from django.utils.timezone import now
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Order, OrderPosition, Organizer,
    Question, Quota, Team, User,
)


class ItemFormTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        t = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_change_items=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')


class CategoriesTest(ItemFormTest):

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/categories/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name_0'] = 'Entry tickets'
        doc = self.post_doc('/control/event/%s/%s/categories/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("Entry tickets", doc.select("#page-wrapper table")[0].text)

    def test_update(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        doc = self.get_doc('/control/event/%s/%s/categories/%s/' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name_0'] = 'T-Shirts'
        doc = self.post_doc('/control/event/%s/%s/categories/%s/' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertIn("T-Shirts", doc.select("#page-wrapper table")[0].text)
        self.assertNotIn("Entry tickets", doc.select("#page-wrapper table")[0].text)
        assert str(ItemCategory.objects.get(id=c.id).name) == 'T-Shirts'

    def test_sort(self):
        c1 = ItemCategory.objects.create(event=self.event1, name="Entry tickets", position=0)
        ItemCategory.objects.create(event=self.event1, name="T-Shirts", position=1)
        doc = self.get_doc('/control/event/%s/%s/categories/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Entry tickets", doc.select("table > tbody > tr")[0].text)
        self.assertIn("T-Shirts", doc.select("table > tbody > tr")[1].text)

        self.client.get('/control/event/%s/%s/categories/%s/down' % (self.orga1.slug, self.event1.slug, c1.id))
        doc = self.get_doc('/control/event/%s/%s/categories/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Entry tickets", doc.select("table > tbody > tr")[1].text)
        self.assertIn("T-Shirts", doc.select("table > tbody > tr")[0].text)

        self.client.get('/control/event/%s/%s/categories/%s/up' % (self.orga1.slug, self.event1.slug, c1.id))
        doc = self.get_doc('/control/event/%s/%s/categories/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Entry tickets", doc.select("table > tbody > tr")[0].text)
        self.assertIn("T-Shirts", doc.select("table > tbody > tr")[1].text)

    def test_delete(self):
        c = ItemCategory.objects.create(event=self.event1, name="Entry tickets")
        doc = self.get_doc('/control/event/%s/%s/categories/%s/delete' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/categories/%s/delete' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("Entry tickets", doc.select("#page-wrapper")[0].text)
        assert not ItemCategory.objects.filter(id=c.id).exists()


class QuestionsTest(ItemFormTest):

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/questions/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['question_0'] = 'What is your shoe size?'
        form_data['type'] = 'N'
        doc = self.post_doc('/control/event/%s/%s/questions/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("shoe size", doc.select("#page-wrapper table")[0].text)

    def test_update_choices(self):
        c = Question.objects.create(event=self.event1, question="What country are you from?", type="C", required=True)
        o1 = c.options.create(answer='Germany')
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['form-TOTAL_FORMS'] = '1'
        form_data['form-INITIAL_FORMS'] = '1'
        form_data['form-MIN_NUM_FORMS'] = '0'
        form_data['form-MAX_NUM_FORMS'] = '1'
        form_data['form-0-id'] = o1.pk
        form_data['form-0-answer_0'] = 'England'
        self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                      form_data)
        c.refresh_from_db()
        assert c.options.exists()
        assert str(c.options.first().answer) == 'England'

    def test_delete_choices(self):
        c = Question.objects.create(event=self.event1, question="What country are you from?", type="C", required=True)
        o1 = c.options.create(answer='Germany')
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['form-TOTAL_FORMS'] = '1'
        form_data['form-INITIAL_FORMS'] = '1'
        form_data['form-MIN_NUM_FORMS'] = '0'
        form_data['form-MAX_NUM_FORMS'] = '1'
        form_data['form-0-id'] = o1.pk
        form_data['form-0-answer_0'] = 'England'
        form_data['form-0-DELETE'] = 'yes'
        self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                      form_data)
        c.refresh_from_db()
        assert not c.options.exists()

    def test_add_choices(self):
        c = Question.objects.create(event=self.event1, question="What country are you from?", type="N", required=True)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['type'] = 'C'
        form_data['form-TOTAL_FORMS'] = '1'
        form_data['form-INITIAL_FORMS'] = '0'
        form_data['form-MIN_NUM_FORMS'] = '0'
        form_data['form-MAX_NUM_FORMS'] = '1'
        form_data['form-0-id'] = ''
        form_data['form-0-answer_0'] = 'Germany'
        self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                      form_data)
        c = Question.objects.get(id=c.id)
        assert c.options.exists()
        assert str(c.options.first().answer) == 'Germany'

    def test_update(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['question_0'] = 'How old are you?'
        doc = self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        self.assertIn("How old", doc.select("#page-wrapper table")[0].text)
        self.assertNotIn("shoe size", doc.select("#page-wrapper table")[0].text)
        c = Question.objects.get(id=c.id)
        self.assertTrue(c.required)
        assert str(Question.objects.get(id=c.id).question) == 'How old are you?'

    def test_sort(self):
        q1 = Question.objects.create(event=self.event1, question="Vegetarian?", type="N", required=True, position=0)
        Question.objects.create(event=self.event1, question="Food allergies?", position=1)
        doc = self.get_doc('/control/event/%s/%s/questions/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Vegetarian?", doc.select("table > tbody > tr")[0].text)
        self.assertIn("Food allergies?", doc.select("table > tbody > tr")[1].text)

        self.client.get('/control/event/%s/%s/questions/%s/down' % (self.orga1.slug, self.event1.slug, q1.id))
        doc = self.get_doc('/control/event/%s/%s/questions/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Vegetarian?", doc.select("table > tbody > tr")[1].text)
        self.assertIn("Food allergies?", doc.select("table > tbody > tr")[0].text)

        self.client.get('/control/event/%s/%s/questions/%s/up' % (self.orga1.slug, self.event1.slug, q1.id))
        doc = self.get_doc('/control/event/%s/%s/questions/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("Vegetarian?", doc.select("table > tbody > tr")[0].text)
        self.assertIn("Food allergies?", doc.select("table > tbody > tr")[1].text)

    def test_delete(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/delete' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/questions/%s/delete' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("shoe size", doc.select("#page-wrapper")[0].text)
        assert not Question.objects.filter(id=c.id).exists()

    def test_question_view(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)

        item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0, position=1)
        o = Order.objects.create(code='FOO', event=self.event1, email='dummy@dummy.test',
                                 status=Order.STATUS_PENDING, datetime=now(),
                                 expires=now() + datetime.timedelta(days=10),
                                 total=14, locale='en')
        op = OrderPosition.objects.create(order=o, item=item1, variation=None, price=Decimal("14"),
                                          attendee_name_parts={'full_name': "Peter"})
        op.answers.create(question=c, answer='42')
        op = OrderPosition.objects.create(order=o, item=item1, variation=None, price=Decimal("14"),
                                          attendee_name_parts={'full_name': "Michael"})
        op.answers.create(question=c, answer='42')
        op = OrderPosition.objects.create(order=o, item=item1, variation=None, price=Decimal("14"),
                                          attendee_name_parts={'full_name': "Petra"})
        op.answers.create(question=c, answer='39')

        doc = self.get_doc('/control/event/%s/%s/questions/%s/' % (self.orga1.slug, self.event1.slug, c.id))
        tbl = doc.select('.container-fluid table.table-bordered tbody')[0]
        assert tbl.select('tr')[0].select('td')[0].text.strip() == '42'
        assert tbl.select('tr')[0].select('td')[1].text.strip() == '2'
        assert tbl.select('tr')[1].select('td')[0].text.strip() == '39'
        assert tbl.select('tr')[1].select('td')[1].text.strip() == '1'

        doc = self.get_doc('/control/event/%s/%s/questions/%s/?status=p' % (self.orga1.slug, self.event1.slug, c.id))
        assert not doc.select('.container-fluid table.table-bordered tbody')

        o.status = Order.STATUS_PAID
        o.save()
        doc = self.get_doc('/control/event/%s/%s/questions/%s/?status=p' % (self.orga1.slug, self.event1.slug, c.id))
        tbl = doc.select('.container-fluid table.table-bordered tbody')[0]
        assert tbl.select('tr')[0].select('td')[0].text.strip() == '42'

    def test_set_dependency(self):
        q1 = Question.objects.create(event=self.event1, question="What country are you from?", type="C", required=True)
        q2 = Question.objects.create(event=self.event1, question="What city are you from?", type="T", required=True)
        o1 = q1.options.create(answer='Germany')
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q2.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['dependency_question'] = q1.pk
        form_data['dependency_value'] = o1.identifier
        doc = self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q2.id),
                            form_data)
        assert doc.select(".alert-success")
        q2.refresh_from_db()
        assert q2.dependency_question == q1
        assert q2.dependency_value == o1.identifier

    def test_set_dependency_circular(self):
        q1 = Question.objects.create(event=self.event1, question="What country are you from?", type="C", required=True)
        o1 = q1.options.create(answer='Germany')
        q2 = Question.objects.create(event=self.event1, question="What city are you from?", type="C", required=True,
                                     dependency_question=q1, dependency_value=o1.identifier)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q1.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['dependency_question'] = q2.pk
        form_data['dependency_value'] = '1'
        doc = self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q1.id),
                            form_data)
        assert not doc.select(".alert-success")

    def test_set_dependency_to_non_choice(self):
        q1 = Question.objects.create(event=self.event1, question="What country are you from?", type="N", required=True)
        q2 = Question.objects.create(event=self.event1, question="What city are you from?", type="T", required=True)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q2.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['dependency_question'] = q1.pk
        form_data['dependency_value'] = '1'
        doc = self.post_doc('/control/event/%s/%s/questions/%s/change' % (self.orga1.slug, self.event1.slug, q2.id),
                            form_data)
        assert not doc.select(".alert-success")


class QuotaTest(ItemFormTest):

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/quotas/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name'] = 'Full house'
        form_data['size'] = '500'
        doc = self.post_doc('/control/event/%s/%s/quotas/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("Full house", doc.select("#page-wrapper table")[0].text)

    def test_update(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0)
        item2 = Item.objects.create(event=self.event1, name="Business", default_price=0)
        ItemVariation.objects.create(item=item2, value="Silver")
        ItemVariation.objects.create(item=item2, value="Gold")
        doc = self.get_doc('/control/event/%s/%s/quotas/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        [i for i in doc.select('[name=itemvars]') if i.get('value') == str(item1.id)][0]['checked'] = 'checked'
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['size'] = '350'
        doc = self.post_doc('/control/event/%s/%s/quotas/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        doc = self.get_doc('/control/event/%s/%s/quotas/' % (self.orga1.slug, self.event1.slug))
        self.assertIn("350", doc.select("#page-wrapper table")[0].text)
        self.assertNotIn("500", doc.select("#page-wrapper table")[0].text)
        assert Quota.objects.get(id=c.id).size == 350
        assert item1 in Quota.objects.get(id=c.id).items.all()

    def test_update_subevent(self):
        self.event1.has_subevents = True
        self.event1.save()
        se1 = self.event1.subevents.create(name="Foo", date_from=now())
        se2 = self.event1.subevents.create(name="Bar", date_from=now())
        c = Quota.objects.create(event=self.event1, name="Full house", size=500, subevent=se1)
        doc = self.get_doc('/control/event/%s/%s/quotas/%s/change' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['subevent'] = se2.pk
        self.post_doc('/control/event/%s/%s/quotas/%s/change' % (self.orga1.slug, self.event1.slug, c.id),
                      form_data)
        assert Quota.objects.get(id=c.id).subevent == se2

    def test_delete(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        doc = self.get_doc('/control/event/%s/%s/quotas/%s/delete' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/quotas/%s/delete' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("Full house", doc.select("#page-wrapper")[0].text)
        assert not Quota.objects.filter(id=c.id).exists()


class ItemsTest(ItemFormTest):

    def setUp(self):
        super().setUp()
        self.item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0, position=1)
        self.item2 = Item.objects.create(event=self.event1, name="Business", default_price=0, position=2,
                                         description="If your ticket is paid by your employer",
                                         active=True, available_until=now() + datetime.timedelta(days=4),
                                         require_voucher=True, allow_cancel=False)
        self.var1 = ItemVariation.objects.create(item=self.item2, value="Silver")
        self.var2 = ItemVariation.objects.create(item=self.item2, value="Gold")
        self.addoncat = ItemCategory.objects.create(event=self.event1, name="Item category")

    def test_move(self):
        self.client.post('/control/event/%s/%s/items/%s/down' % (self.orga1.slug, self.event1.slug, self.item1.id),)
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        assert self.item1.position > self.item2.position
        self.client.post('/control/event/%s/%s/items/%s/up' % (self.orga1.slug, self.event1.slug, self.item1.id),)
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        assert self.item1.position < self.item2.position

    def test_create(self):
        self.client.post('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), {
            'name_0': 'T-Shirt',
            'default_price': '23.00',
            'tax_rate': '19.00'
        })
        resp = self.client.get('/control/event/%s/%s/items/' % (self.orga1.slug, self.event1.slug))
        assert 'T-Shirt' in resp.rendered_content

    def test_update(self):
        self.client.post('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id), {
            'name_0': 'Standard',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes',
            'sales_channels': 'web'
        })
        self.item1.refresh_from_db()
        assert self.item1.default_price == Decimal('23.00')

    def test_manipulate_addons(self):
        self.client.post('/control/event/%s/%s/items/%d/addons' % (self.orga1.slug, self.event1.slug, self.item2.id), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': '',
            'form-0-addon_category': str(self.addoncat.pk),
            'form-0-min_count': '1',
            'form-0-max_count': '2',
        })
        assert self.item2.addons.exists()
        assert self.item2.addons.first().addon_category == self.addoncat
        self.client.post('/control/event/%s/%s/items/%d/addons' % (self.orga1.slug, self.event1.slug, self.item2.id), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.item2.addons.first().pk),
            'form-0-addon_category': str(self.addoncat.pk),
            'form-0-min_count': '1',
            'form-0-max_count': '2',
            'form-0-DELETE': 'on',
        })
        assert not self.item2.addons.exists()

        # Do not allow duplicates
        self.client.post('/control/event/%s/%s/items/%d/addons' % (self.orga1.slug, self.event1.slug, self.item2.id), {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': '',
            'form-0-addon_category': str(self.addoncat.pk),
            'form-0-min_count': '1',
            'form-0-max_count': '2',
            'form-1-id': '',
            'form-1-addon_category': str(self.addoncat.pk),
            'form-1-min_count': '1',
            'form-1-max_count': '2',
        })
        assert not self.item2.addons.exists()

    def test_update_variations(self):
        self.client.post('/control/event/%s/%s/items/%d/variations' % (self.orga1.slug, self.event1.slug, self.item2.id), {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.var1.pk),
            'form-0-value_0': 'Bronze',
            'form-0-active': 'yes',
            'form-1-id': str(self.var2.pk),
            'form-1-value_0': 'Gold',
            'form-1-active': 'yes',
            'name_0': 'form-TOTAL_FORMS',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes'
        })
        self.var1.refresh_from_db()
        assert str(self.var1.value) == 'Bronze'

    def test_delete_variation(self):
        self.client.post('/control/event/%s/%s/items/%d/variations' % (self.orga1.slug, self.event1.slug, self.item2.id), {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.var1.pk),
            'form-0-value_0': 'Bronze',
            'form-0-active': 'yes',
            'form-1-id': str(self.var2.pk),
            'form-1-value_0': 'Gold',
            'form-1-active': 'yes',
            'form-1-DELETE': 'yes',
            'name_0': 'form-TOTAL_FORMS',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes'
        })
        assert not self.item2.variations.filter(pk=self.var2.pk).exists()

    def test_delete(self):
        self.client.post('/control/event/%s/%s/items/%d/delete' % (self.orga1.slug, self.event1.slug, self.item1.id),
                         {})
        assert not self.event1.items.filter(pk=self.item1.pk).exists()
        self.client.post('/control/event/%s/%s/items/%d/delete' % (self.orga1.slug, self.event1.slug, self.item2.id),
                         {})
        assert not self.event1.items.filter(pk=self.item2.pk).exists()

    def test_delete_ordered(self):
        o = Order.objects.create(
            code='FOO', event=self.event1, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + datetime.timedelta(days=10),
            total=14, locale='en'
        )
        OrderPosition.objects.create(
            order=o,
            item=self.item1,
            variation=None,
            price=Decimal("14"),
            attendee_name_parts={'full_name': "Peter"}
        )
        self.client.post('/control/event/%s/%s/items/%d/delete' % (self.orga1.slug, self.event1.slug, self.item1.id),
                         {})
        assert self.event1.items.filter(pk=self.item1.pk).exists()
        self.item1.refresh_from_db()
        assert not self.item1.active

    def test_create_copy(self):
        q = Question.objects.create(event=self.event1, question="Size", type="N")
        q.items.add(self.item2)
        self.item2.sales_channels = ["web", "bar"]

        self.client.post('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), {
            'name_0': 'Intermediate',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'copy_from': str(self.item2.pk),
            'has_variations': '1'
        })
        i_old = Item.objects.get(name__icontains='Business')
        i_new = Item.objects.get(name__icontains='Intermediate')
        assert i_new.category == i_old.category
        assert i_new.description == i_old.description
        assert i_new.active == i_old.active
        assert i_new.available_from == i_old.available_from
        assert i_new.available_until == i_old.available_until
        assert i_new.require_voucher == i_old.require_voucher
        assert i_new.hide_without_voucher == i_old.hide_without_voucher
        assert i_new.allow_cancel == i_old.allow_cancel
        assert i_new.sales_channels == i_old.sales_channels
        assert set(i_new.questions.all()) == set(i_old.questions.all())
        assert set([str(v.value) for v in i_new.variations.all()]) == set([str(v.value) for v in i_old.variations.all()])

    def test_add_to_existing_quota(self):
        q = Quota.objects.create(event=self.event1, name="New Test Quota", size=50)

        doc = self.get_doc('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name_0'] = 'Existing'
        form_data['default_price'] = '2.00'
        form_data['quota_option'] = 'existing'
        form_data['quota_add_existing'] = str(q.pk)
        doc = self.post_doc('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), form_data)

        i = Item.objects.get(name__icontains='Existing')

        assert doc.select(".alert-success")
        assert q.items.filter(pk=i.pk).exists()

    def test_add_to_new_quota(self):
        doc = self.get_doc('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name_0'] = 'New Item'
        form_data['default_price'] = '2.00'
        form_data['quota_option'] = 'new'
        form_data['quota_add_new_name'] = 'New Quota'
        form_data['quota_add_new_size'] = '200'
        doc = self.post_doc('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), form_data)

        assert doc.select(".alert-success")
        assert Quota.objects.filter(name__icontains='New Quota').exists()
        assert Item.objects.filter(name__icontains='New Item').exists()
        i = Item.objects.get(name__icontains='New Item')
        q = Quota.objects.get(name__icontains='New Quota')
        assert q.items.filter(pk=i.pk).exists()
