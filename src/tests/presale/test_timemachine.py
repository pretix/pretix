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
from django_scopes.state import scopes_disabled

from pretix.base.models import Team, User


class TimemachineTestMixin:
    @scopes_disabled()
    def _login_with_permission(self, orga):
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.team1 = Team.objects.create(organizer=orga, can_create_events=True, can_change_event_settings=True,
                                         can_change_items=True, all_events=True)
        self.team1.members.add(self.user)
        self.client.login(email='dummy@dummy.dummy', password='dummy')

    def _set_time_machine_now(self, dt):
        session = self.client.session
        session[f'timemachine_now_dt:{self.event.pk}'] = str(dt)
        session.save()

    def _enable_test_mode(self):
        self.event.testmode = True
        self.event.save()
