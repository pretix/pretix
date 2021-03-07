#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
import re

from django.core.exceptions import ValidationError
from django.core.validators import BaseValidator
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString


class PlaceholderValidator(BaseValidator):
    """
    Takes list of allowed placeholders,
    validates form field by checking for placeholders,
    which are not presented in taken list.
    """

    def __init__(self, limit_value):
        super().__init__(limit_value)
        self.limit_value = limit_value

    def __call__(self, value):
        if isinstance(value, LazyI18nString):
            for l, v in value.data.items():
                self.__call__(v)
            return

        if value.count('{') != value.count('}'):
            raise ValidationError(
                _('Invalid placeholder syntax: You used a different number of "{" than of "}".'),
                code='invalid_placeholder_syntax',
            )

        data_placeholders = list(re.findall(r'({[^}]*})', value, re.X))
        invalid_placeholders = []
        for placeholder in data_placeholders:
            if placeholder not in self.limit_value:
                invalid_placeholders.append(placeholder)
        if invalid_placeholders:
            raise ValidationError(
                _('Invalid placeholder(s): %(value)s'),
                code='invalid_placeholders',
                params={'value': ", ".join(invalid_placeholders,)})

    def clean(self, x):
        return x
