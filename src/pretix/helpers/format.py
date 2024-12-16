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
import logging
from string import Formatter

logger = logging.getLogger(__name__)


class PlainHtmlAlternativeString:
    def __init__(self, plain, html, is_block=False):
        self.plain = plain
        self.html = html
        self.is_block = is_block

    def __repr__(self):
        return f"PlainHtmlAlternativeString('{self.plain}', '{self.html}')"


class SafeFormatter(Formatter):
    """
    Customized version of ``str.format`` that (a) behaves just like ``str.format_map`` and
    (b) does not allow any unwanted shenanigans like attribute access or format specifiers.
    """
    MODE_IGNORE_RICH = 0
    MODE_RICH_TO_PLAIN = 1
    MODE_RICH_TO_HTML = 2

    def __init__(self, context, raise_on_missing=False, mode=MODE_IGNORE_RICH):
        self.context = context
        self.raise_on_missing = raise_on_missing
        self.mode = mode

    def get_field(self, field_name, args, kwargs):
        return self.get_value(field_name, args, kwargs), field_name

    def get_value(self, key, args, kwargs):
        if not self.raise_on_missing and key not in self.context:
            return '{' + str(key) + '}'
        r = self.context[key]
        if isinstance(r, PlainHtmlAlternativeString):
            if self.mode == self.MODE_IGNORE_RICH:
                return '{' + str(key) + '}'
            elif self.mode == self.MODE_RICH_TO_PLAIN:
                return r.plain
            elif self.mode == self.MODE_RICH_TO_HTML:
                return r.html
        return r

    def format_field(self, value, format_spec):
        # Ignore format_spec
        return super().format_field(value, '')


def format_map(template, context, raise_on_missing=False, mode=SafeFormatter.MODE_IGNORE_RICH):
    if not isinstance(template, str):
        template = str(template)
    return SafeFormatter(context, raise_on_missing, mode=mode).format(template)
