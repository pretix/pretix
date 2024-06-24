from bootstrap3.renderers import FieldRenderer
from bootstrap3.text import text_value
from django.forms import CheckboxInput, CheckboxSelectMultiple, RadioSelect
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext


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


class PretixFieldRenderer(FieldRenderer):
    def __init__(self, *args, **kwargs):
        kwargs['layout'] = 'horizontal'
        super().__init__(*args, **kwargs)
        self.is_group_widget = isinstance(self.widget, (CheckboxSelectMultiple, RadioSelect, )) or (self.is_multi_widget and len(self.widget.widgets) > 1)

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
