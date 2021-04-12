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
from django import forms


class Select2Mixin:
    template_name = 'pretixcontrol/select2_widget.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def options(self, name, value, attrs=None):
        if value and value[0]:
            for i, selected in enumerate(self.choices.queryset.filter(pk__in=value)):
                yield self.create_option(
                    None,
                    self.choices.field.prepare_value(selected),
                    self.choices.field.label_from_instance(selected),
                    True,
                    i,
                    subindex=None,
                    attrs=attrs
                )
        return

    def optgroups(self, name, value, attrs=None):
        if value:
            return [
                (None, [c], i)
                for i, c in enumerate(self.options(name, value, attrs))
            ]
        return


class Select2(Select2Mixin, forms.Select):
    pass


class Select2Multiple(Select2Mixin, forms.SelectMultiple):
    pass


class Select2ItemVarQuotaMixin(Select2Mixin):

    def options(self, name, value, attrs=None):
        if value and value[0]:
            yield self.create_option(
                None,
                value[0],
                dict(self.choices)[value[0]],
                True,
                0,
                subindex=None,
                attrs=attrs
            )
        return


class Select2ItemVarQuota(Select2ItemVarQuotaMixin, forms.Select):
    pass
