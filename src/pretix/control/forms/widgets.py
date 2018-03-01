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
