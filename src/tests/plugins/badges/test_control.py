import datetime

from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Item, Organizer, Team, User
from pretix.plugins.badges.models import BadgeItem


class BadgeLayoutFormTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            plugins='pretix.plugins.badges',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
        )
        self.item1 = Item.objects.create(event=self.event1, name="Standard", default_price=0, position=1)
        t = Team.objects.create(organizer=self.orga1, can_change_event_settings=True, can_view_orders=True,
                                can_change_items=True, all_events=True, can_create_events=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_create(self):
        doc = self.get_doc('/control/event/%s/%s/badges/add' % (self.orga1.slug, self.event1.slug))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        form_data['name'] = 'Layout 1'
        doc = self.post_doc('/control/event/%s/%s/badges/add' % (self.orga1.slug, self.event1.slug), form_data)
        assert doc.select(".alert-success")
        self.assertIn("Layout 1", doc.select("#page-wrapper")[0].text)
        assert self.event1.badge_layouts.get(
            default=True, name='Layout 1'
        )

    def test_set_default(self):
        bl1 = self.event1.badge_layouts.create(name="Layout 1", default=True)
        bl2 = self.event1.badge_layouts.create(name="Layout 2")
        self.post_doc('/control/event/%s/%s/badges/%s/default' % (self.orga1.slug, self.event1.slug, bl2.id), {})
        bl1.refresh_from_db()
        assert not bl1.default
        bl2.refresh_from_db()
        assert bl2.default

    def test_delete(self):
        bl1 = self.event1.badge_layouts.create(name="Layout 1", default=True)
        bl2 = self.event1.badge_layouts.create(name="Layout 2")
        doc = self.get_doc('/control/event/%s/%s/badges/%s/delete' % (self.orga1.slug, self.event1.slug, bl1.id))
        form_data = extract_form_fields(doc.select('.container-fluid form')[0])
        doc = self.post_doc('/control/event/%s/%s/badges/%s/delete' % (self.orga1.slug, self.event1.slug, bl1.id),
                            form_data)
        assert doc.select(".alert-success")
        self.assertNotIn("Layout 1", doc.select("#page-wrapper")[0].text)
        assert self.event1.badge_layouts.count() == 1
        bl2.refresh_from_db()
        assert bl2.default

    def test_set_on_item(self):
        self.event1.badge_layouts.create(name="Layout 1", default=True)
        bl2 = self.event1.badge_layouts.create(name="Layout 2")
        self.client.post('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id), {
            'name_0': 'Standard',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes',
            'badgeitem-layout': bl2.pk,
            'sales_channels': 'web',
        })
        assert BadgeItem.objects.get(item=self.item1, layout=bl2)
        self.client.post('/control/event/%s/%s/items/%d/' % (self.orga1.slug, self.event1.slug, self.item1.id), {
            'name_0': 'Standard',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'active': 'yes',
            'allow_cancel': 'yes',
            'sales_channels': 'web',
        })
        assert not BadgeItem.objects.filter(item=self.item1, layout=bl2).exists()

    def test_item_copy(self):
        bl2 = self.event1.badge_layouts.create(name="Layout 2")
        BadgeItem.objects.create(item=self.item1, layout=bl2)
        self.client.post('/control/event/%s/%s/items/add' % (self.orga1.slug, self.event1.slug), {
            'name_0': 'Intermediate',
            'default_price': '23.00',
            'tax_rate': '19.00',
            'copy_from': str(self.item1.pk),
            'has_variations': '1'
        })
        i_new = Item.objects.get(name__icontains='Intermediate')
        assert BadgeItem.objects.get(item=i_new, layout=bl2)
        assert BadgeItem.objects.get(item=self.item1, layout=bl2)

    def test_copy_event(self):
        bl2 = self.event1.badge_layouts.create(name="Layout 2")
        BadgeItem.objects.create(item=self.item1, layout=bl2)
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'foundation',
            'foundation-organizer': self.orga1.pk,
            'foundation-locales': ('en',)
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'basics',
            'basics-name_0': '33C3',
            'basics-slug': '33c3',
            'basics-date_from_0': '2016-12-27',
            'basics-date_from_1': '10:00:00',
            'basics-date_to_0': '2016-12-30',
            'basics-date_to_1': '19:00:00',
            'basics-location_0': 'Hamburg',
            'basics-currency': 'EUR',
            'basics-tax_rate': '19.00',
            'basics-locale': 'en',
            'basics-timezone': 'Europe/Berlin',
        })
        self.post_doc('/control/events/add', {
            'event_wizard-current_step': 'copy',
            'copy-copy_from_event': self.event1.pk
        })

        ev = Event.objects.get(slug='33c3')
        i_new = ev.items.first()
        bl_new = ev.badge_layouts.first()
        assert BadgeItem.objects.get(item=i_new, layout=bl_new)
