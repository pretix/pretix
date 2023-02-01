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
import random

from django.core.cache import cache as django_cache
from django.test import TestCase, override_settings
from django.utils.timezone import now

from pretix.base.models import Event, Organizer


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
})
class CacheTest(TestCase):
    """
    This test case tests the invalidation of the event related
    cache.
    """
    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )
        self.cache = self.event.get_cache()
        randint = random.random()
        self.testkey = "test" + str(randint)

    def test_interference(self):
        django_cache.clear()
        self.cache.set(self.testkey, "foo")
        self.assertIsNone(django_cache.get(self.testkey))
        self.assertIn(self.cache.get(self.testkey), (None, "foo"))

    def test_longkey(self):
        self.cache.set(self.testkey * 100, "foo")
        self.assertEqual(self.cache.get(self.testkey * 100), "foo")

    def test_invalidation(self):
        self.cache.set(self.testkey, "foo")
        self.cache.clear()
        self.assertIsNone(self.cache.get(self.testkey))

    def test_many(self):
        inp = {
            'a': 'foo',
            'b': 'bar',
        }
        self.cache.set_many(inp)
        self.assertEqual(inp, self.cache.get_many(inp.keys()))
