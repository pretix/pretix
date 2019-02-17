from bootstrap3.renderers import FieldRenderer
from bootstrap3.utils import add_css_class


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
