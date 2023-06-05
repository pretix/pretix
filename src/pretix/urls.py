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
# This file contains Apache-licensed contributions copyrighted by: Andreas Teuber, Jonas Große Sundrup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.conf import settings
from django.urls import include, re_path
from django.views.generic import RedirectView

import pretix.control.urls
import pretix.presale.urls
from pretix.base.views import js_helpers

from .base.views import (
    cachedfiles, csp, health, js_catalog, metrics, redirect, source,
)

base_patterns = [
    re_path(r'^download/(?P<id>[^/]+)/$', cachedfiles.DownloadView.as_view(),
            name='cachedfile.download'),
    re_path(r'^healthcheck/$', health.healthcheck,
            name='healthcheck'),
    re_path(r'^redirect/$', redirect.redir_view, name='redirect'),
    re_path(r'^jsi18n/(?P<lang>[a-zA-Z-_]+)/$', js_catalog.js_catalog, name='javascript-catalog'),
    re_path(r'^metrics$', metrics.serve_metrics,
            name='metrics'),
    re_path(r'^csp_report/$', csp.csp_report, name='csp.report'),
    re_path(r'^agpl_source$', source.get_source, name='source'),
    re_path(r'^js_helpers/states/$', js_helpers.states, name='js_helpers.states'),
    re_path(r'^api/v1/', include(('pretix.api.urls', 'pretixapi'), namespace='api-v1')),
    re_path(r'^api/$', RedirectView.as_view(url='/api/v1/'), name='redirect-api-version')
]

control_patterns = [
    re_path(r'^control/', include((pretix.control.urls, 'control'))),
]

debug_patterns = []
if settings.DEBUG:
    try:
        import debug_toolbar

        debug_patterns.append(re_path(r'^__debug__/', include(debug_toolbar.urls)))
    except ImportError:
        pass

common_patterns = base_patterns + control_patterns + debug_patterns
