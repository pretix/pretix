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


class SafeFormatter(Formatter):
    """
    Customized version of ``str.format`` that (a) behaves just like ``str.format_map`` and
    (b) does not allow any unwanted shenanigans like attribute access or format specifiers.
    """
    def __init__(self, context):
        self.context = context

    def get_field(self, field_name, args, kwargs):
        if '.' in field_name or '[' in field_name:
            logger.warning(f'Ignored invalid field name "{field_name}"')
            return ('{' + str(field_name) + '}', field_name)
        return super().get_field(field_name, args, kwargs)

    def get_value(self, key, args, kwargs):
        if key not in self.context:
            return '{' + str(key) + '}'
        return self.context[key]

    def format_field(self, value, format_spec):
        # Ignore format _spec
        return super().format_field(value, '')


def format_map(template, context):
    if not isinstance(template, str):
        template = str(template)
    return SafeFormatter(context).format(template)
