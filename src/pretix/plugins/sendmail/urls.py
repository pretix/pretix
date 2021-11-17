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
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.conf.urls import re_path

from pretix.api.urls import event_router

from . import views
from .api import RuleViewSet

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/$', views.SenderView.as_view(),
            name='send'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/history/', views.EmailHistoryView.as_view(),
            name='history'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/rules/create', views.CreateRule.as_view(),
            name='rule.create'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/rules/(?P<rule>[^/]+)/schedule',
            views.ScheduleView.as_view(),
            name='rule.schedule'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/rules/(?P<rule>[^/]+)/delete',
            views.DeleteRule.as_view(),
            name='rule.delete'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/rules/(?P<rule>[^/]+)',
            views.UpdateRule.as_view(),
            name='rule.update'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sendmail/rules', views.ListRules.as_view(),
            name='rule.list'),
]
event_router.register(r'sendmail_rules', RuleViewSet)
