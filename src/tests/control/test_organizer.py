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
import datetime

import pytest
from django.db import transaction
from django_scopes import scopes_disabled
from tests.base import SoupTest, extract_form_fields

from pretix.base.models import Event, Organizer, Team, User


@pytest.fixture
def class_monkeypatch(request, monkeypatch):
    request.cls.monkeypatch = monkeypatch


@pytest.mark.usefixtures("class_monkeypatch")
class OrganizerTest(SoupTest):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.orga1 = Organizer.objects.create(name='CCC', slug='ccc')
        self.orga2 = Organizer.objects.create(name='MRM', slug='mrm')
        self.event1 = Event.objects.create(
            organizer=self.orga1, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            plugins='pretix.plugins.banktransfer,tests.testdummy'
        )

        t = Team.objects.create(organizer=self.orga1, can_create_events=True, can_change_event_settings=True,
                                can_change_items=True, can_change_organizer_settings=True)
        t.members.add(self.user)
        t.limit_events.add(self.event1)

        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def test_organizer_list(self):
        doc = self.get_doc('/control/organizers/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("CCC", tabletext)
        self.assertNotIn("MRM", tabletext)

    def test_organizer_detail(self):
        doc = self.get_doc('/control/organizer/ccc/')
        tabletext = doc.select("#page-wrapper .table")[0].text
        self.assertIn("30C3", tabletext)

    def test_organizer_settings(self):
        doc = self.get_doc('/control/organizer/%s/edit' % (self.orga1.slug,))
        doc.select("[name=name]")[0]['value'] = "CCC e.V."

        doc = self.post_doc('/control/organizer/%s/edit' % (self.orga1.slug,),
                            extract_form_fields(doc.select('.container-fluid form')[0]))
        assert len(doc.select(".alert-success")) > 0
        assert doc.select("[name=name]")[0]['value'] == "CCC e.V."
        self.orga1.refresh_from_db()
        assert self.orga1.name == "CCC e.V."

    def test_organizer_display_settings(self):
        called = False

        def set_called(*args, **kwargs):
            nonlocal called
            called = True

        self.monkeypatch.setattr("pretix.presale.style.regenerate_organizer_css.apply_async", set_called)
        assert not self.orga1.settings.presale_css_checksum
        doc = self.get_doc('/control/organizer/%s/edit' % (self.orga1.slug,))
        doc.select("[name=settings-primary_color]")[0]['value'] = "#33c33c"

        with transaction.atomic():
            doc = self.post_doc('/control/organizer/%s/edit' % (self.orga1.slug,),
                                extract_form_fields(doc.select('.container-fluid form')[0]))
            assert len(doc.select(".alert-success")) > 0
            assert doc.select("[name=settings-primary_color]")[0]['value'] == "#33c33c"
        self.orga1.settings.flush()
        assert self.orga1.settings.primary_color == "#33c33c"
        assert called
