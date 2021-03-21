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
from django.apps import AppConfig
from django.urls import URLPattern
from django.urls.resolvers import RegexPattern


class PretixMultidomainConfig(AppConfig):
    name = 'pretix.multidomain'
    label = 'pretixmultidomain'


default_app_config = 'pretix.multidomain.PretixMultidomainConfig'


def event_url(route, view, name=None, require_live=True):
    if callable(view):
        pattern = RegexPattern(route, name=name, is_endpoint=True)
        pattern._require_live = require_live
        return URLPattern(pattern, view, {}, name)
    raise TypeError('view must be a callable.')
