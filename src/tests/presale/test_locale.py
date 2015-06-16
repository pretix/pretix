from django.test import TestCase


class LocaleTest(TestCase):

    def test_set_locale_cookie(self):
        response = self.client.get('/control/login')
        assert response['Content-Language'] == 'en'
        self.client.get('/locale/set?locale=de')
        assert self.client.get('/')
        assert response['Content-Language'] == 'de'
