from django import forms
from rest_framework import serializers


class FormFieldWrapperField(serializers.Field):
    def __init__(self, *args, **kwargs):
        self.form_field = kwargs.pop('form_field')
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        return self.form_field.widget.format_value(value)

    def to_internal_value(self, data):
        d = self.form_field.widget.value_from_datadict({'name': data}, {}, 'name')
        d = self.form_field.clean(d)
        return d


simple_mappings = (
    (forms.DateField, serializers.DateField, tuple()),
    (forms.TimeField, serializers.TimeField, tuple()),
    (forms.SplitDateTimeField, serializers.DateTimeField, tuple()),
    (forms.DateTimeField, serializers.DateTimeField, tuple()),
    (forms.DecimalField, serializers.DecimalField, ('max_digits', 'decimal_places', 'min_value', 'max_value')),
    (forms.FloatField, serializers.FloatField, tuple()),
    (forms.IntegerField, serializers.IntegerField, tuple()),
    (forms.EmailField, serializers.EmailField, tuple()),
    (forms.UUIDField, serializers.UUIDField, tuple()),
    (forms.URLField, serializers.URLField, tuple()),
    (forms.NullBooleanField, serializers.NullBooleanField, tuple()),
    (forms.BooleanField, serializers.BooleanField, tuple()),
)


class ExporterSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    verbose_name = serializers.CharField()
    input_fields = serializers.ListField(serializers.CharField())


class JobRunSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        ex = kwargs.pop('exporter')
        super().__init__(*args, **kwargs)
        for k, v in ex.export_form_fields.items():
            for m_from, m_to, m_kwargs in simple_mappings:
                if isinstance(v, m_from):
                    self.fields[k] = m_to(
                        required=v.required,
                        allow_null=not v.required,
                        validators=v.validators,
                        **{kwarg: getattr(v, kwargs, None) for kwarg in m_kwargs}
                    )
                    break

            if isinstance(v, forms.ModelMultipleChoiceField):
                self.fields[k] = serializers.PrimaryKeyRelatedField(
                    queryset=v.queryset,
                    required=v.required,
                    allow_empty=not v.required,
                    validators=v.validators,
                    many=True
                )
            elif isinstance(v, forms.ModelChoiceField):
                self.fields[k] = serializers.PrimaryKeyRelatedField(
                    queryset=v.queryset,
                    required=v.required,
                    allow_null=not v.required,
                    validators=v.validators,
                )
            elif isinstance(v, forms.MultipleChoiceField):
                self.fields[k] = serializers.MultipleChoiceField(
                    choices=v.choices,
                    required=v.required,
                    allow_empty=not v.required,
                    validators=v.validators,
                )
            elif isinstance(v, forms.ChoiceField):
                self.fields[k] = serializers.ChoiceField(
                    choices=v.choices,
                    required=v.required,
                    allow_null=not v.required,
                    validators=v.validators,
                )
            else:
                self.fields[k] = FormFieldWrapperField(form_field=v, required=v.required, allow_null=not v.required)
