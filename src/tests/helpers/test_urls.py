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
from django import urls
from django.conf import settings

from pretix.helpers.urls import build_absolute_uri


def test_site_url_domain():
    settings.SITE_URL = 'https://example.com'
    assert build_absolute_uri('control:auth.login') == 'https://example.com/control/login'


def test_site_url_subpath():
    settings.SITE_URL = 'https://example.com/presale'
    old_prefix = urls.get_script_prefix()
    urls.set_script_prefix('/presale/')
    assert build_absolute_uri('control:auth.login') == 'https://example.com/presale/control/login'
    urls.set_script_prefix(old_prefix)
