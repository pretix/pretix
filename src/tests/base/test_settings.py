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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.test import TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base import settings
from pretix.base.models import Event, Organizer
from pretix.base.settings import SettingsSandbox
from pretix.control.forms.global_settings import GlobalSettingsObject


class SettingsTestCase(TestCase):
    def setUp(self):
        settings.DEFAULTS['test_default'] = {
            'default': 'def',
            'type': str
        }
        self.global_settings = GlobalSettingsObject()
        self.global_settings.settings.flush()
        self.organizer = Organizer.objects.create(name='Dummy', slug='dummy')
        self.organizer.settings.flush()
        self.event = Event.objects.create(
            organizer=self.organizer, name='Dummy', slug='dummy',
            date_from=now(),
        )
        self.event.settings.flush()

    def _test_serialization(self, val, as_type):
        self.event.settings.set('test', val)
        self.event.settings.flush()
        self.assertEqual(self.event.settings.get('test', as_type=as_type), val)
        self.assertIsInstance(self.event.settings.get('test', as_type=as_type), as_type)

    def test_serialize_lazyi18nstring(self):
        self._test_serialization(LazyI18nString({'de': 'Hallo', 'en': 'Hello'}), LazyI18nString)

    def test_sandbox(self):
        sandbox = SettingsSandbox('testing', 'foo', self.event)
        sandbox.set('foo', 'bar')
        self.assertEqual(sandbox.get('foo'), 'bar')
        self.assertEqual(self.event.settings.get('testing_foo_foo'), 'bar')
        self.assertIsNone(self.event.settings.get('foo'), 'bar')

        sandbox['bar'] = 'baz'
        sandbox.baz = 42

        with scopes_disabled():
            self.event = Event.objects.get(id=self.event.id)
        sandbox = SettingsSandbox('testing', 'foo', self.event)
        self.assertEqual(sandbox['bar'], 'baz')
        self.assertEqual(sandbox.baz, '42')

        del sandbox.baz
        del sandbox['bar']

        self.assertIsNone(sandbox.bar)
        self.assertIsNone(sandbox['baz'])
