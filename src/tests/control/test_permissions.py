from django.test import TestCase, Client
from django.utils.timezone import now

from pretix.base.models import Event, Organizer, User, EventPermission


class PermissionMiddlewareTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """

    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')

    def test_logged_out(self):
        c = Client()
        response = c.get('/control/login')
        self.assertEqual(response.status_code, 200)
        response = c.get('/control/events/')
        self.assertEqual(response.status_code, 302)

    def test_wrong_event(self):
        c = Client()
        response = c.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

        response = c.get('/control/event/dummy/dummy/settings/')
        self.assertIn(response.status_code, (403, 404))

    def test_wrong_event_permission(self):
        EventPermission.objects.create(
            event=self.event, user=self.user,
            can_change_settings=False,
            can_change_items=True,
        )
        c = Client()
        response = c.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

        response = c.get('/control/event/dummy/dummy/settings/')
        self.assertIn(response.status_code, (403, 404))

    def test_correct(self):
        EventPermission.objects.create(
            event=self.event, user=self.user,
            can_change_settings=True,
            can_change_items=True,
        )
        c = Client()
        response = c.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

        response = c.get('/control/event/dummy/dummy/settings/')
        self.assertEqual(response.status_code, 200)
