from bootstrap3.renderers import FieldRenderer
from bootstrap3.text import text_value
from bootstrap3.utils import add_css_class
from django.forms import CheckboxInput
from django.forms.utils import flatatt
from django.utils.html import escape, format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext


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
        # usually checkboxes have overall empty labels and special labels per checkbox 
        # => remove for-attribute as well as "required"-text appended to label
        del(attrs['for'])
        opt = ""
    else:
        opt = mark_safe('<i class="sr-only"> {}</i>'.format(pgettext('form', 'required'))) if not optional else ''

    builder = '<{tag}{attrs}>{content}{opt}</{tag}>'
    return format_html(
        builder,
        tag='label',
        attrs=mark_safe(flatatt(attrs)) if attrs else '',
        opt=opt,
        content=text_value(content),
    )


class CheckoutFieldRenderer(FieldRenderer):
    def __init__(self, *args, **kwargs):
        kwargs['layout'] = 'horizontal'
        super().__init__(*args, **kwargs)

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

    def add_label(self, html):
        label = self.get_label()

        if hasattr(self.field.field, '_required'):
            # e.g. payment settings forms where a field is only required if the payment provider is active
            required = self.field.field._required
        else:
            required = self.field.field.required

        html = render_label(
            label,
            label_for=self.field.id_for_label,
            label_class=self.get_label_class(),
            optional=not required #and not isinstance(self.widget, CheckboxInput)
        ) + html
        return html

    def put_inside_label(self, html):
        content = "{field} {label}".format(field=html, label=self.label)
        return render_label(
            content=mark_safe(content),
            label_for=self.field.id_for_label,
            label_title=escape(strip_tags(self.field_help)),
        )