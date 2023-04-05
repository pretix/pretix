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
import json
import re

from django.conf import settings
from django.utils import translation
from django.utils.formats import get_format

date_conversion_to_moment = {
    '%a': 'ddd',
    '%A': 'dddd',
    '%w': 'd',
    '%d': 'DD',
    '%b': 'MMM',
    '%B': 'MMMM',
    '%m': 'MM',
    '%y': 'YY',
    '%Y': 'YYYY',
    '%H': 'HH',
    '%I': 'hh',
    '%p': 'a',
    '%M': 'mm',
    '%S': 'ss',
    '%f': 'SSSSSS',
    '%z': 'ZZ',
    '%Z': 'zz',
    '%j': 'DDDD',
    '%U': 'ww',  # fuzzy translation
    '%W': 'WW',
    '%c': '',
    '%x': '',
    '%X': ''
}

out_date_conversion_to_moment = {
    'a': 'a',
    'A': 'A',
    'b': 'MMM',
    'c': 'YYYY-MM-DDTHH:mm:ss.SSSSSSZ',
    'd': 'DD',
    'e': 'zz',
    'E': 'MMMM',
    'f': 'h:mm',
    'F': 'MMMM',
    'g': 'h',
    'G': 'H',
    'h': 'hh',
    'H': 'HH',
    'i': 'mm',
    'I': '',
    'j': 'D',
    'l': 'dddd',
    'L': '',
    'm': 'MM',
    'M': 'MMM',
    'n': 'M',
    'N': 'MMM',  # fuzzy
    'o': 'GGGG',
    'O': 'ZZ',
    'P': 'h:mm a',
    'r': 'ddd, D MMM YYYY HH:mm:ss Z',
    's': 'ss',
    'S': 'Do',  # fuzzy
    't': '',
    'T': 'z',
    'u': 'SSSSSS',
    'U': 'X',
    'w': 'd',
    'W': 'W',
    'y': 'YY',
    'Y': 'YYYY',
    'z': 'DDD',
    'Z': ''

}

moment_locales = {
    'af', 'az', 'bs', 'de-at', 'en-gb', 'et', 'fr-ch', 'hi', 'it', 'ko', 'me', 'ms-my', 'pa-in', 'se', 'sr', 'th',
    'tzm-latn', 'zh-hk', 'ar', 'be', 'ca', 'de', 'en-ie', 'eu', 'fr', 'hr', 'ja', 'ky', 'mi', 'my', 'pl', 'si', 'ss',
    'tlh', 'uk', 'zh-tw', 'ar-ly', 'bg', 'cs', 'dv', 'en-nz', 'fa', 'fy', 'hu', 'jv', 'lb', 'mk', 'nb', 'pt-br', 'sk',
    'sv', 'tl-ph', 'uz', 'ar-ma', 'bn', 'cv', 'el', 'eo', 'fi', 'gd', 'hy-am', 'ka', 'lo', 'ml', 'ne', 'pt', 'sl', 'sw',
    'tr', 'vi', 'ar-sa', 'bo', 'cy', 'en-au', 'es-do', 'fo', 'gl', 'id', 'kk', 'lt', 'mr', 'nl', 'ro', 'sq', 'ta',
    'tzl', 'x-pseudo', 'ar-tn', 'br', 'da', 'en-ca', 'es', 'fr-ca', 'he', 'is', 'km', 'lv', 'ms', 'nn', 'ru', 'sr-cyrl',
    'te', 'tzm', 'zh-cn',
}

toJavascript_re = re.compile(r'(?<!\w)(' + '|'.join(date_conversion_to_moment.keys()) + r')\b')  # noqa
toJavascriptOut_re = re.compile(r'(?<!\w)(' + '|'.join(out_date_conversion_to_moment.keys()) + r')\b')  # noqa


def get_javascript_output_format(format_name):
    f = get_format(format_name)
    if not isinstance(f, str):
        f = f[0]
    return toJavascriptOut_re.sub(
        lambda x: out_date_conversion_to_moment[x.group()],
        f
    )


def get_javascript_format(format_name):
    f = get_format(format_name)
    if not isinstance(f, str):
        f = f[0]
    return toJavascript_re.sub(
        lambda x: date_conversion_to_moment[x.group()],
        f
    )


def get_format_without_seconds(format_name):
    formats = get_format(format_name)
    formats_no_seconds = [f for f in formats if '%S' not in f]
    return formats_no_seconds[0] if formats_no_seconds else formats[0]


def get_javascript_format_without_seconds(format_name):
    f = get_format_without_seconds(format_name)
    return toJavascript_re.sub(
        lambda x: date_conversion_to_moment[x.group()],
        f
    )


def get_moment_locale(locale=None):
    cur_lang = locale or translation.get_language()
    cur_lang = cur_lang.lower()
    if cur_lang in moment_locales:
        return cur_lang
    if '-' in cur_lang or '_' in cur_lang:
        main = cur_lang.replace("_", "-").split("-")[0]
        if main in moment_locales:
            return main
    return settings.LANGUAGE_CODE


def i18ncomp(query):
    return json.dumps(str(query))[1:-1]
