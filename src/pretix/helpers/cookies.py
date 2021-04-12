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
import re

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
    if should_send_same_site_none(request.headers.get('User-Agent', '')):
        # Chromium is rolling out SameSite=Lax as a default
        # https://www.chromestatus.com/feature/5088147346030592
        # This however breaks all pretix-in-an-iframe things, such as the pretix Widget.
        # Sadly, this means we need to forcefully set SameSite=None and rely on our other
        # CSRF protections to be working.
        response.cookies[key]['samesite'] = 'None'
        # This will only work on secure cookies as well
        # https://www.chromestatus.com/feature/5633521622188032
        response.cookies[key]['secure'] = is_secure


# Based on https://www.chromium.org/updates/same-site/incompatible-clients
# Copyright 2019 Google LLC.
# SPDX-License-Identifier: Apache-2.0


def should_send_same_site_none(useragent):
    # Don’t send `SameSite=None` to known incompatible clients.
    return not has_web_kit_same_site_bug(useragent) and not drops_unrecognized_same_site_cookies(useragent)


def has_web_kit_same_site_bug(useragent):
    return is_ios_version(12, useragent) or (
        is_macosx_version(10, 14, useragent) and (is_safari(useragent) or is_mac_embedded_browser(useragent))
    )


def drops_unrecognized_same_site_cookies(useragent):
    if is_uc_browser(useragent):
        return not is_uc_browser_version_at_least(12, 13, 2, useragent)
    return (
        is_chromium_based(useragent) and is_chromium_version_at_least(51, useragent) and
        not is_chromium_version_at_least(67, useragent)
    )


# Regex parsing of User-Agent string. (See note above!)
RE_CHROMIUM = re.compile(r"Chrom(e|ium)")
RE_CHROMIUM_VERSION = re.compile(r"Chrom[^ /]+[ /]([0-9]+)[.0-9]*")
RE_UC_VERSION = re.compile(r"UC[ ]?Browser/([0-9]+)\.([0-9]+)\.([0-9]+)[.0-9]*")
RE_IOS_VERSION = re.compile(r"\(iP.+; CPU .*OS ([0-9]+)[_0-9]*.*\) AppleWebKit/")
RE_MAC_VERSION = re.compile(r"\(Macintosh;.*Mac OS X ([0-9]+)_([0-9]+)[_0-9]*.*\) AppleWebKit/")
RE_SAFARI = re.compile(r"Version/.* Safari/")
RE_MAC_EMBEDDED = re.compile(r"^Mozilla/[.0-9]+ \(Macintosh;.*Mac OS X [_0-9]+\) AppleWebKit/[.0-9]+ \(KHTML, "
                             r"like Gecko\)$")


def is_ios_version(major, useragent):
    m = RE_IOS_VERSION.search(useragent)
    if not m:
        return False
    return m.group(1) == str(major)


def is_macosx_version(major, minor, useragent):
    m = RE_MAC_VERSION.search(useragent)
    if not m:
        return False

    return m.group(1) == str(major) and m.group(2) == str(minor)


def is_safari(useragent):
    return RE_SAFARI.search(useragent) and not is_chromium_based(useragent)


def is_mac_embedded_browser(useragent):
    return RE_MAC_EMBEDDED.search(useragent)


def is_chromium_based(useragent):
    return RE_CHROMIUM.search(useragent)


def is_chromium_version_at_least(major, useragent):
    # Extract digits from first capturing group.
    match = RE_CHROMIUM_VERSION.search(useragent)
    if not match:
        return False
    version = int(match.group(1))
    return version >= major


def is_uc_browser(useragent):
    return 'UCBrowser/' in useragent


def is_uc_browser_version_at_least(major, minor, build, useragent):
    major_version = int(RE_UC_VERSION.search(useragent).group(1))
    minor_version = int(RE_UC_VERSION.search(useragent).group(2))
    build_version = int(RE_UC_VERSION.search(useragent).group(3))
    if major_version != major:
        return major_version > major
    if minor_version != minor:
        return minor_version > minor
    return build_version >= build
