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
from django.http import HttpResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_page


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
