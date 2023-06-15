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
# This file contains Apache-licensed contributions copyrighted by: Tim Freund
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import importlib.util

from django.apps import apps
from django.urls import include, re_path
from django.views.generic import TemplateView

from pretix.multidomain.plugin_handler import plugin_event_urls
from pretix.presale.urls import (
    event_patterns, locale_patterns, organizer_patterns,
)
from pretix.urls import common_patterns

presale_patterns_main = [
    re_path(r'', include((locale_patterns + [
        re_path(r'^(?P<organizer>[^/]+)/', include(organizer_patterns)),
        re_path(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(event_patterns)),
        re_path(r'^$', TemplateView.as_view(template_name='pretixpresale/index.html'), name="index")
    ], 'presale')))
]

raw_plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            single_plugin_patterns = []
            if hasattr(urlmod, 'urlpatterns'):
                single_plugin_patterns += urlmod.urlpatterns
            if hasattr(urlmod, 'event_patterns'):
                patterns = plugin_event_urls(urlmod.event_patterns, plugin=app.name)
                single_plugin_patterns.append(re_path(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/',
                                                      include(patterns)))
            if hasattr(urlmod, 'organizer_patterns'):
                patterns = plugin_event_urls(urlmod.organizer_patterns, plugin=app.name)
                single_plugin_patterns.append(re_path(r'^(?P<organizer>[^/]+)/',
                                                      include(patterns)))
            raw_plugin_patterns.append(
                re_path(r'', include((single_plugin_patterns, app.label)))
            )

plugin_patterns = [
    re_path(r'', include((raw_plugin_patterns, 'plugins')))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + plugin_patterns + presale_patterns_main

handler404 = 'pretix.base.views.errors.page_not_found'
handler500 = 'pretix.base.views.errors.server_error'
