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
from bootstrap3.renderers import FieldRenderer, InlineFieldRenderer
from bootstrap3.text import text_value
from django.forms import CheckboxInput, CheckboxSelectMultiple, RadioSelect
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext
from i18nfield.forms import I18nFormField


def render_label(content, label_for=None, label_class=None, label_title='', label_id='', optional=False):
    """
    Render a label with content
    """
    attrs = {}
    if label_for:
        attrs['for'] = label_for
    if label_class:
        attrs['class'] = label_class
    if label_title:
        attrs['title'] = label_title
    if label_id:
        attrs['id'] = label_id

    if text_value(content) == '&#160;':
        # Empty label, e.g. checkbox
        attrs.setdefault('class', '')
        attrs['class'] += ' label-empty'

    builder = '<{tag}{attrs}>{content}{opt}</{tag}>'
    return format_html(
        builder,
        tag='label',
        attrs=mark_safe(flatatt(attrs)) if attrs else '',
        opt=mark_safe('<br><span class="optional">{}</span>'.format(pgettext('form', 'Optional'))) if optional else '',
        content=text_value(content),
    )


class ControlFieldRenderer(FieldRenderer):
    def __init__(self, *args, **kwargs):
        kwargs['layout'] = 'horizontal'
        super().__init__(*args, **kwargs)
        self.is_group_widget = isinstance(self.widget, (CheckboxSelectMultiple, RadioSelect, )) or (self.is_multi_widget and len(self.widget.widgets) > 1)

    def add_label(self, html):
        label = self.get_label()

        if hasattr(self.field.field, '_required'):
            # e.g. payment settings forms where a field is only required if the payment provider is active
            required = self.field.field._required
        elif isinstance(self.field.field, I18nFormField):
            required = self.field.field.one_required
        else:
            required = self.field.field.required

        if self.is_group_widget:
            label_for = ""
            label_id = "legend-{}".format(self.field.html_name)
        else:
            label_for = self.field.id_for_label
            label_id = ""

        html = render_label(
            label,
            label_for=label_for,
            label_class=self.get_label_class(),
            label_id=label_id,
            optional=not required and not isinstance(self.widget, CheckboxInput)
        ) + html
        return html

    def wrap_label_and_field(self, html):
        if self.is_group_widget:
            attrs = ' role="group" aria-labelledby="legend-{}"'.format(self.field.html_name)
        else:
            attrs = ''
        return '<div class="{klass}"{attrs}>{html}</div>'.format(klass=self.get_form_group_class(), html=html, attrs=attrs)

    def wrap_widget(self, html):
        if isinstance(self.widget, CheckboxInput):
            css_class = "checkbox"
            if self.field.field.disabled:
                css_class += " disabled"
            html = f'<div class="{css_class}">{html}</div>'
        return html


class ControlFieldWithVisibilityRenderer(ControlFieldRenderer):
    def __init__(self, *args, **kwargs):
        kwargs['layout'] = 'horizontal'
        kwargs['horizontal_field_class'] = 'col-md-7'
        self.visibility_field = kwargs['visibility_field']
        super().__init__(*args, **kwargs)

    def render_visibility_field(self):
        return self.visibility_field.as_widget(attrs=self.visibility_field.field.widget.attrs)

    def wrap_field(self, html):
        html = super().wrap_field(html)
        html += '<div class="col-md-2 text-right">' + self.render_visibility_field() + '</div>'
        return html


class BulkEditMixin:

    def __init__(self, *args, **kwargs):
        kwargs['layout'] = self.layout
        super().__init__(*args, **kwargs)

    def wrap_field(self, html):
        field_class = self.get_field_class()
        name = '{}{}'.format(self.field.form.prefix, self.field.name)
        checked = self.field.form.data and name in self.field.form.data.getlist('_bulk')
        html = (
            '<div class="{klass} bulk-edit-field-group">'
            '<label class="field-toggle">'
            '<input type="checkbox" name="_bulk" value="{name}" {checked}> {label}'
            '</label>'
            '<div class="field-content">'
            '{html}'
            '</div>'
            '</div>'
        ).format(
            klass=field_class or '',
            name=name,
            label=pgettext('form_bulk', 'change'),
            checked='checked' if checked else '',
            html=html
        )
        return html


class BulkEditFieldRenderer(BulkEditMixin, FieldRenderer):
    layout = 'horizontal'


class InlineBulkEditFieldRenderer(BulkEditMixin, InlineFieldRenderer):
    layout = 'inline'
