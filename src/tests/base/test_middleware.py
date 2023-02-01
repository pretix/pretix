#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.conf import settings
from django.test import Client, TestCase
from django.utils.timezone import now

from pretix.base.models import Event, Organizer, User


class LocaleDeterminationTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """
    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(), live=True
        )
        self.TEST_LOCALE = 'de' if settings.LANGUAGE_CODE == 'en' else 'en'
        self.TEST_LOCALE_LONG = 'de-AT' if settings.LANGUAGE_CODE == 'en' else 'en-NZ'
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')

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

    def test_event_allowed(self):
        self.event.settings.set('locales', ['de', 'en'])
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = 'de'
        response = c.get('/dummy/dummy/')
        language = response['Content-Language']
        self.assertEqual(language, 'de')

    def test_event_fallback_to_short(self):
        self.event.settings.set('locales', ['de'])
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = 'de-informal'
        response = c.get('/dummy/dummy/')
        language = response['Content-Language']
        self.assertEqual(language, 'de')

    def test_event_fallback_to_long(self):
        self.event.settings.set('locales', ['de-informal'])
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = 'de'
        response = c.get('/dummy/dummy/')
        language = response['Content-Language']
        self.assertEqual(language, 'de-informal')

    def test_event_not_allowed(self):
        self.event.settings.set('locales', ['en'])
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = 'de'
        response = c.get('/dummy/dummy/')
        language = response['Content-Language']
        self.assertEqual(language, 'en')
