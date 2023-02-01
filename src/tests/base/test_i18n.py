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
from django.test import TestCase
from django.utils import translation
from django.utils.timezone import now
from i18nfield.strings import LazyI18nString

from pretix.base.models import Event, ItemCategory, Organizer


class I18nStringTest(TestCase):
    """
    This test case tests the LazyI18nString class
    """

    def test_explicit_translation(self):
        data = {
            'de': 'Hallo',
            'en': 'Hello'
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hallo')

    def test_similar_translations(self):
        data = {
            'en': 'You',
            'de': 'Sie',
            'de-informal': 'Du'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Sie')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Du')

        data = {
            'en': 'You',
            'de-informal': 'Du'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Du')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Du')

        data = {
            'en': 'You',
            'de': 'Sie'
        }
        s = LazyI18nString(data)
        translation.activate('de')
        self.assertEqual(str(s), 'Sie')
        translation.activate('de-informal')
        self.assertEqual(str(s), 'Sie')

    def test_missing_default_translation(self):
        data = {
            'de': 'Hallo',
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hallo')
        translation.activate('de')
        self.assertEqual(str(s), 'Hallo')

    def test_missing_translation(self):
        data = {
            'en': 'Hello',
        }
        s = LazyI18nString(data)
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hello')

    def test_legacy_string(self):
        s = LazyI18nString("Hello")
        translation.activate('en')
        self.assertEqual(str(s), 'Hello')
        translation.activate('de')
        self.assertEqual(str(s), 'Hello')

    def test_none(self):
        s = LazyI18nString(None)
        self.assertEqual(str(s), "")
        s = LazyI18nString("")
        self.assertEqual(str(s), "")


class I18nFieldTest(TestCase):
    """
    This test case tests the I18n*Field classes
    """
    def setUp(self):
        o = Organizer.objects.create(name='Dummy', slug='dummy')
        self.event = Event.objects.create(
            organizer=o, name='Dummy', slug='dummy',
            date_from=now(),
        )

    def test_save_load_cycle_plain_string(self):
        obj = ItemCategory.objects.create(event=self.event, name="Hello")
        obj = ItemCategory.objects.get(id=obj.id)
        self.assertIsInstance(obj.name, LazyI18nString)
        translation.activate('en')
        self.assertEqual(str(obj.name), "Hello")
        translation.activate('de')
        self.assertEqual(str(obj.name), "Hello")

    def test_save_load_cycle_i18n_string(self):
        obj = ItemCategory.objects.create(event=self.event,
                                          name=LazyI18nString(
                                              {
                                                  'de': 'Hallo',
                                                  'en': 'Hello'
                                              }
                                          ))
        obj = ItemCategory.objects.get(id=obj.id)
        self.assertIsInstance(obj.name, LazyI18nString)
        translation.activate('en')
        self.assertEqual(str(obj.name), "Hello")
        translation.activate('de')
        self.assertEqual(str(obj.name), "Hallo")
