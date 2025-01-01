from i18nfield.fields import I18nCharField, I18nTextField
from rest_framework.fields import Field
from rest_framework.serializers import ModelSerializer


class I18nFlattenedField(Field):
    def __init__(self, **kwargs):
        self.allow_blank = kwargs.pop("allow_blank", False)
        self.trim_whitespace = kwargs.pop("trim_whitespace", True)
        self.max_length = kwargs.pop("max_length", None)
        self.min_length = kwargs.pop("min_length", None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return str(value)

    def to_internal_value(self, data):
        raise TypeError("Input not supported.")


class I18nFlattenedModelSerializer(ModelSerializer):
    pass


I18nFlattenedModelSerializer.serializer_field_mapping[I18nCharField] = (
    I18nFlattenedField
)
I18nFlattenedModelSerializer.serializer_field_mapping[I18nTextField] = (
    I18nFlattenedField
)
