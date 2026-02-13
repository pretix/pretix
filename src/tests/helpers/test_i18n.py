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
import pytest
from django.utils.translation import get_language

from pretix.base.i18n import (
    get_babel_locale, get_language_without_region, language,
)
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


@pytest.mark.parametrize(
    ["lng_in", "region_in", "lng_out", "lng_without_region_out", "babel_out"],
    [
        ("en", None, "en", "en", "en"),
        ("en-us", None, "en-us", "en", "en_US"),
        ("en", "US", "en-us", "en", "en_US"),
        ("de", None, "de", "de", "de"),
        ("de", "US", "de-us", "de", "de"),
        ("de", "DE", "de-de", "de", "de_DE"),
        ("de-informal", "DE", "de-informal", "de-informal", "de_DE"),
        ("de-informal", "CH", "de-informal", "de-informal", "de_CH"),
        ("pt-pt", "PT", "pt-pt", "pt-pt", "pt_PT"),
        ("es", "MX", "es-mx", "es", "es_MX"),
        ("es-419", "MX", "es-419", "es-419", "es_MX"),
        ("zh-hans", "US", "zh-hans", "zh-hans", "zh_Hans"),
        ("zh-hans", "CN", "zh-hans", "zh-hans", "zh_Hans_CN"),
        ("zh-hant", "TW", "zh-hant", "zh-hant", "zh_Hant_TW"),
    ],
)
def test_set_region(lng_in, region_in, lng_out, lng_without_region_out, babel_out):
    with language(lng_in, region_in):
        assert get_language() == lng_out
        assert get_language_without_region() == lng_without_region_out
        assert str(get_babel_locale()) == babel_out
