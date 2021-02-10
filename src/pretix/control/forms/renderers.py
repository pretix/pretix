from bootstrap3.renderers import FieldRenderer, InlineFieldRenderer
from bootstrap3.text import text_value
from django.forms import CheckboxInput
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext
from i18nfield.forms import I18nFormField


def render_label(content, label_for=None, label_class=None, label_title='', optional=False):
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

    def add_label(self, html):
        label = self.get_label()

        if hasattr(self.field.field, '_required'):
            # e.g. payment settings forms where a field is only required if the payment provider is active
            required = self.field.field._required
        elif isinstance(self.field.field, I18nFormField):
            required = self.field.field.one_required
        else:
            required = self.field.field.required

        html = render_label(
            label,
            label_for=self.field.id_for_label,
            label_class=self.get_label_class(),
            optional=not required and not isinstance(self.widget, CheckboxInput)
        ) + html
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
