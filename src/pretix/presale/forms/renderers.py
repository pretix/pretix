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
from bootstrap3.utils import add_css_class
from django.utils.html import escape, strip_tags
from django.utils.safestring import mark_safe

from pretix.base.forms.renderers import PretixFieldRenderer


class CheckoutFieldRenderer(PretixFieldRenderer):
    def get_form_group_class(self):
        form_group_class = self.form_group_class
        if self.field.errors:
            if self.error_css_class:
                form_group_class = add_css_class(form_group_class, self.error_css_class)
        else:
            if self.field.form.is_bound:
                form_group_class = add_css_class(form_group_class, self.success_css_class)
        required = (getattr(self.field.field, '_show_required', False) or getattr(self.field.field, '_required', False) or self.field.field.required)
        if required and self.required_css_class:
            form_group_class = add_css_class(form_group_class, self.required_css_class)
        if self.layout == 'horizontal':
            form_group_class = add_css_class(
                form_group_class,
                self.get_size_class(prefix='form-group')
            )
        return form_group_class

    def append_to_field(self, html):
        help_text_and_errors = []
        help_text_and_errors += self.field_errors
        if self.field_help:
            help_text_and_errors.append(self.field_help)
        for idx, text in enumerate(help_text_and_errors):
            if text.lower().startswith("<p>") or text.lower().startswith("<p "):
                html_tag = "div"
            else:
                html_tag = "p"
            html += '<{tag} class="help-block" id="help-for-{id}-{idx}">{text}</{tag}>'.format(id=self.field.id_for_label, text=text, idx=idx, tag=html_tag)
        return html

    def add_help_attrs(self, widget=None):
        super().add_help_attrs(widget)
        if widget is None:
            widget = self.widget
        help_cnt = len(self.field_errors)
        if self.field_help:
            help_cnt += 1
        if help_cnt > 0:
            help_ids = ["help-for-{id}-{idx}".format(id=self.field.id_for_label, idx=idx) for idx in range(help_cnt)]
            widget.attrs["aria-describedby"] = " ".join(help_ids)

    def put_inside_label(self, html):
        content = "{field} {label}".format(field=html, label=self.label)
        return render_label(
            content=mark_safe(content),
            label_for=self.field.id_for_label,
            label_title=escape(strip_tags(self.field_help)),
        )
