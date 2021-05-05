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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze, Unicorn-rzl
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from contextlib import contextmanager

from babel import localedata
from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext

from pretix.base.templatetags.money import money_filter

from i18nfield.fields import (  # noqa
    I18nCharField, I18nTextarea, I18nTextField, I18nTextInput,
)
from i18nfield.forms import I18nFormField  # noqa
# Compatibility imports
from i18nfield.strings import LazyI18nString  # noqa
from i18nfield.utils import I18nJSONEncoder  # noqa


class LazyDate:
    def __init__(self, value):
        self.value = value

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return date_format(self.value, "SHORT_DATE_FORMAT")


class LazyExpiresDate:
    def __init__(self, expires):
        self.value = expires

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        at_end_of_day = self.value.hour == 23 and self.value.minute == 59 and self.value.second >= 59
        if at_end_of_day:
            return date_format(self.value, "SHORT_DATE_FORMAT")
        else:
            return date_format(self.value, "SHORT_DATETIME_FORMAT")


class LazyCurrencyNumber:
    def __init__(self, value, currency):
        self.value = value
        self.currency = currency

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return money_filter(self.value, self.currency)


class LazyNumber:
    def __init__(self, value, decimal_pos=2):
        self.value = value
        self.decimal_pos = decimal_pos

    def __format__(self, format_spec):
        return self.__str__()

    def __str__(self):
        return number_format(self.value, decimal_pos=self.decimal_pos)


ALLOWED_LANGUAGES = dict(settings.LANGUAGES)


def get_babel_locale():
    babel_locale = 'en'
    # Babel, and therefore django-phonenumberfield, do not support our custom locales such das de_Informal
    if translation.get_language():
        if localedata.exists(translation.get_language()):
            babel_locale = translation.get_language()
        elif localedata.exists(translation.get_language()[:2]):
            babel_locale = translation.get_language()[:2]
    return babel_locale


def get_language_without_region(lng=None):
    """
    Returns the currently active language, but strips what pretix calls a ``region``. For example,
    if the currently active language is ``en-us``, you will be returned ``en`` since pretix does not
    ship with separate language files for ``en-us``. If the currently active language is ``pt-br``,
    you will be returned ``pt-br`` since there are separate language files for ``pt-br``.

    tl;dr: You will be always passed a language that is defined in settings.LANGUAGES.
    """
    lng = lng or translation.get_language() or settings.LANGUAGE_CODE
    if lng not in ALLOWED_LANGUAGES:
        lng = lng.split('-')[0]
    if lng not in ALLOWED_LANGUAGES:
        lng = settings.LANGUAGE_CODE
    return lng


@contextmanager
def language(lng, region=None):
    """
    Temporarily change the active language to ``lng``. Will automatically be rolled back when the
    context manager returns.

    You can optionally pass a "region". For example, if you pass ``en`` as ``lng`` and ``US`` as
    ``region``, the active language will be ``en-us``, which will mostly affect date/time
    formatting. If you pass a ``lng`` that already contains a region, e.g. ``pt-br``, the ``region``
    attribute will be ignored.
    """
    _lng = translation.get_language()
    lng = lng or settings.LANGUAGE_CODE
    if '-' not in lng and region:
        lng += '-' + region.lower()
    translation.activate(lng)
    try:
        yield
    finally:
        translation.activate(_lng)


class LazyLocaleException(Exception):
    def __init__(self, *args):
        self.msg = args[0]
        self.msgargs = args[1] if len(args) > 1 else None
        self.args = args
        super().__init__(self.msg, self.msgargs)

    def __str__(self):
        if self.msgargs:
            return gettext(self.msg) % self.msgargs
        else:
            return gettext(self.msg)
