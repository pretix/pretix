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
from django.utils.translation import get_language

from pretix.base.i18n import get_language_without_region, language
from pretix.helpers.i18n import get_javascript_format, get_moment_locale


def test_js_formats():
    with language('de'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'DD.MM.YYYY'
    with language('en'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'YYYY-MM-DD'
    with language('en-US'):
        assert get_javascript_format('DATE_INPUT_FORMATS') == 'MM/DD/YYYY'


def test_get_locale():
    assert get_moment_locale('af') == 'af'
    assert get_moment_locale('de_Informal') == 'de'
    assert get_moment_locale('de-US') == 'de'
    assert get_moment_locale('en-US') == 'en'
    assert get_moment_locale('en-CA') == 'en-ca'


def test_set_region():
    with language('de'):
        assert get_language() == 'de'
        assert get_language_without_region() == 'de'
    with language('de', 'US'):
        assert get_language() == 'de-us'
        assert get_language_without_region() == 'de'
    with language('de', 'DE'):
        assert get_language() == 'de-de'
        assert get_language_without_region() == 'de'
    with language('de-informal', 'DE'):
        assert get_language() == 'de-informal'
        assert get_language_without_region() == 'de-informal'
    with language('pt', 'PT'):
        assert get_language() == 'pt-pt'
        assert get_language_without_region() == 'pt-pt'
    with language('pt-pt', 'BR'):
        assert get_language() == 'pt-pt'
        assert get_language_without_region() == 'pt-pt'
