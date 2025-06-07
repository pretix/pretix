from django import forms
from rest_framework import serializers

from pretix.base.timeframes import DateFrameField, SerializerDateFrameField

simple_mappings = (
    (forms.DateField, serializers.DateField, ()),
    (forms.TimeField, serializers.TimeField, ()),
    (forms.SplitDateTimeField, serializers.DateTimeField, ()),
    (forms.DateTimeField, serializers.DateTimeField, ()),
    (forms.DecimalField, serializers.DecimalField, ('max_digits', 'decimal_places', 'min_value', 'max_value')),
    (forms.FloatField, serializers.FloatField, ()),
    (forms.IntegerField, serializers.IntegerField, ()),
    (forms.EmailField, serializers.EmailField, ()),
    (forms.UUIDField, serializers.UUIDField, ()),
    (forms.URLField, serializers.URLField, ()),
    (forms.BooleanField, serializers.BooleanField, ()),
)


class PrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        if isinstance(value, int):
            return value
        return super().to_representation(value)


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


def form_field_to_serializer_field(field):
    for m_from, m_to, m_kwargs in simple_mappings:
        if isinstance(field, m_from):
            return m_to(
                required=field.required,
                allow_null=not field.required,
                validators=field.validators,
                **{kwarg: getattr(field, kwarg, None) for kwarg in m_kwargs}
            )

    if isinstance(field, forms.NullBooleanField):
        return serializers.BooleanField(
            required=field.required,
            allow_null=True,
            validators=field.validators,
        )
    if isinstance(field, forms.ModelMultipleChoiceField):
        return PrimaryKeyRelatedField(
            queryset=field.queryset,
            required=field.required,
            allow_empty=not field.required,
            validators=field.validators,
            many=True
        )
    elif isinstance(field, forms.ModelChoiceField):
        return PrimaryKeyRelatedField(
            queryset=field.queryset,
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, forms.MultipleChoiceField):
        return serializers.MultipleChoiceField(
            choices=field.choices,
            required=field.required,
            allow_empty=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, forms.ChoiceField):
        return serializers.ChoiceField(
            choices=field.choices,
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    elif isinstance(field, DateFrameField):
        return SerializerDateFrameField(
            required=field.required,
            allow_null=not field.required,
            validators=field.validators,
        )
    else:
        return FormFieldWrapperField(form_field=field, required=field.required, allow_null=not field.required)
