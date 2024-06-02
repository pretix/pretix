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
import hashlib
import time

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.templatetags.static import static
from django.utils.http import http_date
from django.views.decorators.cache import cache_page
from django.views.decorators.gzip import gzip_page
from django.views.decorators.http import condition

from pretix.presale.style import get_theme_vars_css

# we never change static source without restart, so we can cache this thread-wise
_source_cache_key = None


def _get_source_cache_key():
    global _source_cache_key
    if not _source_cache_key:
        with open(finders.find("pretixbase/scss/_variables.scss"), "r") as f:
            _source_cache_key = hashlib.sha256(f.read().encode()).hexdigest()[:12]
    return _source_cache_key


@cache_page(3600)
def browserconfig_xml(request):
    return HttpResponse(
        """<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
    <msapplication>
        <tile>
            <square150x150logo src="{}"/>
            <square310x310logo src="{}"/>
            <TileColor>#3b1c4a</TileColor>
        </tile>
    </msapplication>
</browserconfig>""".format(
            static('pretixbase/img/icons/mstile-150x150.png'),
            static('pretixbase/img/icons/mstile-310x310.png'),
        ), content_type='text/xml'
    )


@cache_page(3600)
def webmanifest(request):
    return HttpResponse(
        """{
    "name": "",
    "short_name": "",
    "icons": [
        {
            "src": "%s",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "%s",
            "sizes": "512x512",
            "type": "image/png"
        }
    ],
    "theme_color": "#3b1c4a",
    "background_color": "#3b1c4a",
    "display": "standalone"
}""" % (
            static('pretixbase/img/icons/android-chrome-192x192.png'),
            static('pretixbase/img/icons/android-chrome-512x512.png'),
        ), content_type='text/json'
    )


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
