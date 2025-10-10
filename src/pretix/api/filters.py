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
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.constants import LOOKUP_SEP
from django.forms import MultipleChoiceField
from django_filters import Filter
from django_filters.conf import settings


class MultipleCharField(forms.CharField):
    widget = forms.MultipleHiddenInput

    def to_python(self, value):
        if not value:
            return []
        elif not isinstance(value, (list, tuple)):
            raise ValidationError(
                MultipleChoiceField.default_error_messages["invalid_list"], code="invalid_list"
            )
        return [str(val) for val in value]


class MultipleCharFilter(Filter):
    """
    This filter performs OR(by default) or AND(using conjoined=True) query
    on the selected inputs.
    """

    field_class = MultipleCharField

    def __init__(self, *args, **kwargs):
        self.conjoined = kwargs.pop("conjoined", False)
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if not value:
            # Even though not a noop, no point filtering if empty.
            return qs

        if not self.conjoined:
            q = Q()
        for v in set(value):
            predicate = self.get_filter_predicate(v)
            if self.conjoined:
                qs = self.get_method(qs)(**predicate)
            else:
                q |= Q(**predicate)

        if not self.conjoined:
            qs = self.get_method(qs)(q)

        return qs.distinct() if self.distinct else qs

    def get_filter_predicate(self, v):
        name = self.field_name
        if name and self.lookup_expr != settings.DEFAULT_LOOKUP_EXPR:
            name = LOOKUP_SEP.join([name, self.lookup_expr])
        try:
            return {name: getattr(v, self.field.to_field_name)}
        except (AttributeError, TypeError):
            return {name: v}
