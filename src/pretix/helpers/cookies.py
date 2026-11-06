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
import itertools
import re
from http.cookies import Morsel

from django.conf import settings


def set_cookie_without_samesite(request, response, key, *args, **kwargs):
    assert 'samesite' not in kwargs
    response.set_cookie(key, *args, **kwargs)
    is_secure = (
        kwargs.get('secure', False) or request.scheme == 'https' or
        settings.SITE_URL.startswith('https://')
    )
    if not is_secure:
        # https://www.chromestatus.com/feature/5633521622188032
        return
    if should_send_same_site_none(UserAgent(request.headers.get('User-Agent', ''))):
        # Chromium is rolling out SameSite=Lax as a default
        # https://www.chromestatus.com/feature/5088147346030592
        # This however breaks all pretix-in-an-iframe things, such as the pretix Widget.
        # Sadly, this means we need to forcefully set SameSite=None and rely on our other
        # CSRF protections to be working.
        response.cookies[key]['samesite'] = 'None'
        # This will only work on secure cookies as well
        # https://www.chromestatus.com/feature/5633521622188032
        response.cookies[key]['secure'] = is_secure
        # CHIPS
        response.cookies[key]['Partitioned'] = True


def thoroughly_delete_cookie(response, cookie_name, **kwargs):
    """ Deletes different possible versions of a cookie (SameSite, Partitioned) """
    properties = {"SameSite": ["", 'None'], "Partitioned": ["", True]}
    for i, values in enumerate(itertools.product(*properties.values())):
        m = Morsel()
        m.set(cookie_name, '', '')
        m.update(kwargs)
        m.update(zip(properties.keys(), values))
        m['expires'] = "Thu, 01 Jan 1970 00:00:00 GMT"

        response.cookies[f'___DELETECOOKIE__{i}___{cookie_name}'] = m

    # Make sure settings a cookie afterwards will add a new item in the dictionary, placing
    # it below our deletion headers.
    response.cookies.pop(cookie_name, None)


def get_all_values_of_cookie(cookie_header, cookie_name):
    # like django.http.cookie.parse_cookie, but returns all values of duplicated cookies instead of only the last
    values = list()
    if not cookie_header:
        return values
    for chunk in cookie_header.split(";"):
        if "=" in chunk:
            key, val = chunk.split("=", 1)
        else:
            # Assume an empty name per
            # https://bugzilla.mozilla.org/show_bug.cgi?id=169091
            key, val = "", chunk
        key, val = key.strip(), val.strip()
        if key == cookie_name:
            values.append(val)
    return values


# Based on https://www.chromium.org/updates/same-site/incompatible-clients
# Copyright 2019 Google LLC.
# SPDX-License-Identifier: Apache-2.0


def should_send_same_site_none(useragent: "UserAgent") -> bool:
    # Don’t send `SameSite=None` to known incompatible clients.
    return not has_web_kit_same_site_bug(useragent) and not drops_unrecognized_same_site_cookies(useragent)


def has_web_kit_same_site_bug(ua: "UserAgent") -> bool:
    return ua.ios_major_version == 12 or (
        ua.macosx_version == (10, 14) and (ua.is_safari or ua.is_mac_embedded_browser)
    )


def drops_unrecognized_same_site_cookies(ua: "UserAgent") -> bool:
    if ua.uc_browser_version:
        return ua.uc_browser_version < (12, 13, 2)
    return ua.chromium_major_version and 51 <= ua.chromium_major_version < 67


class UserAgent:
    # Regex parsing of User-Agent string. (See note above!)
    RE_CHROMIUM = re.compile(r"Chrom(e|ium)")
    RE_CHROMIUM_VERSION = re.compile(r"Chrom[^ /]+[ /]([0-9]+)[.0-9]*")
    RE_UC_VERSION = re.compile(r"UC[ ]?Browser/([0-9]+)\.([0-9]+)\.([0-9]+)[.0-9]*")
    RE_IOS_VERSION = re.compile(r"\(iP.+; CPU .*OS ([0-9]+)[_0-9]*.*\) AppleWebKit/")
    RE_MAC_VERSION = re.compile(r"\(Macintosh;.*Mac OS X ([0-9]+)_([0-9]+)[_0-9]*.*\) AppleWebKit/")
    RE_SAFARI = re.compile(r"Version/.* Safari/")
    RE_MAC_EMBEDDED = re.compile(r"^Mozilla/[.0-9]+ \(Macintosh;.*Mac OS X [_0-9]+\) AppleWebKit/[.0-9]+ \(KHTML, "
                                 r"like Gecko\)$")

    def __init__(self, useragent):
        self.useragent = useragent

    @property
    def ios_major_version(self):
        m = UserAgent.RE_IOS_VERSION.search(self.useragent)
        if not m:
            return None
        return int(m.group(1))

    @property
    def macosx_version(self):
        m = UserAgent.RE_MAC_VERSION.search(self.useragent)
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)))

    @property
    def is_safari(self):
        return UserAgent.RE_SAFARI.search(self.useragent) and not self.is_chromium_based

    @property
    def is_mac_embedded_browser(self):
        return UserAgent.RE_MAC_EMBEDDED.search(self.useragent)

    @property
    def is_chromium_based(self):
        return UserAgent.RE_CHROMIUM.search(self.useragent)

    @property
    def chromium_major_version(self):
        # Extract digits from first capturing group.
        match = UserAgent.RE_CHROMIUM_VERSION.search(self.useragent)
        if not match:
            return None
        return int(match.group(1))

    @property
    def uc_browser_version(self):
        m = UserAgent.RE_UC_VERSION.search(self.useragent)
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
