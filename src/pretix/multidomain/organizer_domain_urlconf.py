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
import importlib.util

from django.apps import apps
from django.urls import include, re_path

from pretix.multidomain.plugin_handler import plugin_event_urls
from pretix.presale.urls import (
    event_patterns, locale_patterns, organizer_patterns,
)
from pretix.urls import common_patterns

presale_patterns = [
    re_path(r'', include((locale_patterns + [
        re_path(r'', include(organizer_patterns)),
        re_path(r'^(?P<event>[^/]+)/', include(event_patterns)),
    ], 'presale')))
]

raw_plugin_patterns = []
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            urlmod = importlib.import_module(app.name + '.urls')
            single_plugin_patterns = []

            if hasattr(urlmod, 'organizer_patterns'):
                single_plugin_patterns += plugin_event_urls(urlmod.organizer_patterns, plugin=app.name)

            if hasattr(urlmod, 'event_patterns'):
                plugin_event_patterns = plugin_event_urls(urlmod.event_patterns, plugin=app.name)
                single_plugin_patterns.append(
                    re_path(r'^(?P<event>[^/]+)/', include(plugin_event_patterns))
                )

            if single_plugin_patterns:
                raw_plugin_patterns.append(
                    re_path(r'', include((single_plugin_patterns, app.label)))
                )

plugin_patterns = [
    re_path(r'', include((raw_plugin_patterns, 'plugins')))
]

# The presale namespace comes last, because it contains a wildcard catch
urlpatterns = common_patterns + plugin_patterns + presale_patterns

handler404 = 'pretix.base.views.errors.page_not_found'
handler500 = 'pretix.base.views.errors.server_error'
