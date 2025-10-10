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
import hashlib
import time

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.utils.http import http_date
from django.views.decorators.gzip import gzip_page
from django.views.decorators.http import condition

from pretix.presale.style import get_theme_vars_css

# we never change static source without restart, so we can cache this thread-wise
_source_cache_key = None


def _get_source_cache_key():
    global _source_cache_key
    if not _source_cache_key:
        with open(finders.find("pretixbase/scss/_theme_variables.scss"), "r") as f:
            _source_cache_key = hashlib.sha256(f.read().encode()).hexdigest()[:12]
    return _source_cache_key


@gzip_page
@condition(etag_func=lambda request, **kwargs: request.GET.get("version"))
def theme_css(request, **kwargs):
    obj = getattr(request, "event", request.organizer)
    css = get_theme_vars_css(obj, widget=False)
    resp = HttpResponse(css, content_type="text/css")
    resp._csp_ignore = True
    resp["Access-Control-Allow-Origin"] = "*"
    if "version" in request.GET:
        resp["Expires"] = http_date(time.time() + 3600 * 24 * 30)
    return resp
