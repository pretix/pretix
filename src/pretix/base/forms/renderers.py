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
from bootstrap3.renderers import (
    FieldRenderer as BaseFieldRenderer,
    InlineFieldRenderer as BaseInlineFieldRenderer,
)
from django.forms import (
    CheckboxInput, CheckboxSelectMultiple, ClearableFileInput, RadioSelect,
    SelectDateWidget,
)


class FieldRenderer(BaseFieldRenderer):
    # Local application of https://github.com/zostera/django-bootstrap3/pull/859

    def post_widget_render(self, html):
        if isinstance(self.widget, CheckboxSelectMultiple):
            html = self.list_to_class(html, "checkbox")
        elif isinstance(self.widget, RadioSelect):
            html = self.list_to_class(html, "radio")
        elif isinstance(self.widget, SelectDateWidget):
            html = self.fix_date_select_input(html)
        elif isinstance(self.widget, ClearableFileInput):
            html = self.fix_clearable_file_input(html)
        elif isinstance(self.widget, CheckboxInput):
            html = self.put_inside_label(html)
        return html


class InlineFieldRenderer(BaseInlineFieldRenderer):
    # Local application of https://github.com/zostera/django-bootstrap3/pull/859

    def post_widget_render(self, html):
        if isinstance(self.widget, CheckboxSelectMultiple):
            html = self.list_to_class(html, "checkbox")
        elif isinstance(self.widget, RadioSelect):
            html = self.list_to_class(html, "radio")
        elif isinstance(self.widget, SelectDateWidget):
            html = self.fix_date_select_input(html)
        elif isinstance(self.widget, ClearableFileInput):
            html = self.fix_clearable_file_input(html)
        elif isinstance(self.widget, CheckboxInput):
            html = self.put_inside_label(html)
        return html
