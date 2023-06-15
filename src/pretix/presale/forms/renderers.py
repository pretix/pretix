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
from bootstrap3.text import text_value
from bootstrap3.utils import add_css_class
from django.forms import CheckboxInput, CheckboxSelectMultiple, RadioSelect
from django.forms.utils import flatatt
from django.utils.html import escape, format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext

from pretix.base.forms.renderers import FieldRenderer


def render_label(content, label_for=None, label_class=None, label_title='', label_id='', optional=False, is_valid=None, attrs=None):
    """
    Render a label with content
    """
    attrs = attrs or {}
    if label_for:
        attrs['for'] = label_for
    if label_class:
        attrs['class'] = label_class
    if label_title:
        attrs['title'] = label_title
    if label_id:
        attrs['id'] = label_id

    opt = ""

    if is_valid is not None:
        if is_valid:
            validation_text = pgettext('form', 'is valid')
        else:
            validation_text = pgettext('form', 'has errors')
        opt += '<strong class="sr-only"> {}</strong>'.format(validation_text)

    if text_value(content) == '&#160;':
        # Empty label, e.g. checkbox
        attrs.setdefault('class', '')
        attrs['class'] += ' label-empty'
        # usually checkboxes have overall empty labels and special labels per checkbox
        # => remove for-attribute as well as "required"-text appended to label
        if 'for' in attrs:
            del attrs['for']
    else:
        opt += '<i class="sr-only label-required">, {}</i>'.format(pgettext('form', 'required')) if not optional else ''

    builder = '<{tag}{attrs}>{content}{opt}</{tag}>'
    return format_html(
        builder,
        tag='label',
        attrs=mark_safe(flatatt(attrs)) if attrs else '',
        opt=mark_safe(opt),
        content=text_value(content),
    )


class CheckoutFieldRenderer(FieldRenderer):
    def __init__(self, *args, **kwargs):
        kwargs['layout'] = 'horizontal'
        super().__init__(*args, **kwargs)
        self.is_group_widget = isinstance(self.widget, (CheckboxSelectMultiple, RadioSelect, )) or (self.is_multi_widget and len(self.widget.widgets) > 1)

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

    def add_label(self, html):
        attrs = {}
        label = self.get_label()

        if hasattr(self.field.field, '_show_required'):
            # e.g. payment settings forms where a field is only required if the payment provider is active
            required = self.field.field._show_required
        elif hasattr(self.field.field, '_required'):
            # e.g. payment settings forms where a field is only required if the payment provider is active
            required = self.field.field._required
        else:
            required = self.field.field.required

        if self.field.form.is_bound:
            is_valid = len(self.field.errors) == 0
        else:
            is_valid = None

        if self.is_group_widget:
            label_for = ""
            label_id = "legend-{}".format(self.field.html_name)
        else:
            label_for = self.field.id_for_label
            label_id = ""

        if hasattr(self.field.field, 'question') and self.field.field.question.identifier:
            attrs["data-identifier"] = self.field.field.question.identifier

        html = render_label(
            label,
            label_for=label_for,
            label_class=self.get_label_class(),
            label_id=label_id,
            attrs=attrs,
            optional=not required and not isinstance(self.widget, CheckboxInput),
            is_valid=is_valid
        ) + html
        return html

    def put_inside_label(self, html):
        content = "{field} {label}".format(field=html, label=self.label)
        return render_label(
            content=mark_safe(content),
            label_for=self.field.id_for_label,
            label_title=escape(strip_tags(self.field_help)),
        )

    def wrap_label_and_field(self, html):
        if self.is_group_widget:
            attrs = ' role="group" aria-labelledby="legend-{}"'.format(self.field.html_name)
        else:
            attrs = ''
        return '<div class="{klass}"{attrs}>{html}</div>'.format(klass=self.get_form_group_class(), html=html, attrs=attrs)
