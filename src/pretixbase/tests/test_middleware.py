from django.test import TestCase, Client
from django.utils.timezone import now
from django.conf import settings

from pretixbase.models import Event, Organizer, User


class LocaleDeterminationTest(TestCase):
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
        self.TEST_LOCALE = 'de' if settings.LANGUAGE_CODE == 'en' else 'en'
        self.TEST_LOCALE_LONG = 'de-AT' if settings.LANGUAGE_CODE == 'en' else 'en-NZ'
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy@dummy.dummy', 'dummy')

    def test_global_default(self):
        c = Client()
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, settings.LANGUAGE_CODE)

    def test_browser_default(self):
        c = Client(HTTP_ACCEPT_LANGUAGE=self.TEST_LOCALE)
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, self.TEST_LOCALE)

        c = Client(HTTP_ACCEPT_LANGUAGE=self.TEST_LOCALE_LONG)
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, self.TEST_LOCALE)

    def test_unknown_browser_default(self):
        c = Client(HTTP_ACCEPT_LANGUAGE='sjn')
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, settings.LANGUAGE_CODE)

    def test_cookie_settings(self):
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = self.TEST_LOCALE
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, self.TEST_LOCALE)

        cookies[settings.LANGUAGE_COOKIE_NAME] = self.TEST_LOCALE_LONG
        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, self.TEST_LOCALE)

    def test_user_settings(self):
        c = Client()
        self.user.locale = self.TEST_LOCALE
        self.user.save()
        response = c.post('/control/login', {
            'email': 'dummy@dummy.dummy',
            'password': 'dummy',
        })
        self.assertEqual(response.status_code, 302)

        response = c.get('/control/login')
        language = response['Content-Language']
        self.assertEqual(language, self.TEST_LOCALE)
