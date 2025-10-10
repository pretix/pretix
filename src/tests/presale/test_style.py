#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import datetime

from django.test import TestCase
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


class StyleTest(TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            live=True
        )

    def test_organizer_generate_css_for_inherited_events(self):
        self.orga.settings.primary_color = "#33c33c"
        c = self.client.get("/ccc/theme.css").content.decode()
        assert '#33c33c' in c

        c = self.client.get("/ccc/30c3/theme.css").content.decode()
        assert '#33c33c' in c

    def test_organizer_generate_css_only_for_inherited_events(self):
        self.orga.settings.primary_color = "#33c33c"
        self.event.settings.primary_color = "#34c34c"

        c = self.client.get("/ccc/theme.css").content.decode()
        assert '#33c33c' in c

        c = self.client.get("/ccc/30c3/theme.css").content.decode()
        assert '#34c34c' in c
        assert '#33c33c' not in c
