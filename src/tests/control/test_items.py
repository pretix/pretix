import datetime

from tests.base import SoupTest, extract_form_fields

from pretix.base.models import (
    Event, EventPermission, Item, ItemCategory, ItemVariation, Organizer,
    OrganizerPermission, Question, Quota, User,
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
        OrganizerPermission.objects.create(organizer=self.orga1, user=self.user)
        EventPermission.objects.create(event=self.event1, user=self.user, can_change_items=True,
                                       can_change_settings=True)
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

    def test_update(self):
        c = Question.objects.create(event=self.event1, question="What is your shoe size?", type="N", required=True)
        doc = self.get_doc('/control/event/%s/%s/questions/%s/' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['question_0'] = 'How old are you?'
        doc = self.post_doc('/control/event/%s/%s/questions/%s/' % (self.orga1.slug, self.event1.slug, c.id), form_data)
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
        doc = self.get_doc('/control/event/%s/%s/quotas/%s/' % (self.orga1.slug, self.event1.slug, c.id))
        doc.select('[name=item_%s]' % item1.id)[0]['checked'] = 'checked'
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['size'] = '350'
        doc = self.post_doc('/control/event/%s/%s/quotas/%s/' % (self.orga1.slug, self.event1.slug, c.id), form_data)
        self.assertIn("350", doc.select("#page-wrapper table")[0].text)
        self.assertNotIn("500", doc.select("#page-wrapper table")[0].text)
        assert Quota.objects.get(id=c.id).size == 350
        assert item1 in Quota.objects.get(id=c.id).items.all()

    def test_delete(self):
        c = Quota.objects.create(event=self.event1, name="Full house", size=500)
        doc = self.get_doc('/control/event/%s/%s/quotas/%s/delete' % (self.orga1.slug, self.event1.slug, c.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/quotas/%s/delete' % (self.orga1.slug, self.event1.slug, c.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("Full house", doc.select("#page-wrapper")[0].text)
        assert not Quota.objects.filter(id=c.id).exists()
