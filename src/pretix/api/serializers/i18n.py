from django.conf import settings
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.strings import LazyI18nString
from rest_framework.exceptions import ValidationError
from rest_framework.fields import Field
from rest_framework.serializers import ModelSerializer


class I18nField(Field):
    def __init__(self, **kwargs):
        self.allow_blank = kwargs.pop('allow_blank', False)
        self.trim_whitespace = kwargs.pop('trim_whitespace', True)
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if value is None or value.data is None:
            return None
        if isinstance(value.data, dict):
            return value.data
        else:
            return {
                settings.LANGUAGE_CODE: str(value.data)
            }

    def to_internal_value(self, data):
        if isinstance(data, str):
            return LazyI18nString(data)
        elif isinstance(data, dict):
            if any([k not in dict(settings.LANGUAGES) for k in data.keys()]):
                raise ValidationError('Invalid languages included.')
            return LazyI18nString(data)
        else:
            raise ValidationError('Invalid data type.')


class I18nAwareModelSerializer(ModelSerializer):
    pass


I18nAwareModelSerializer.serializer_field_mapping[I18nCharField] = I18nField
I18nAwareModelSerializer.serializer_field_mapping[I18nTextField] = I18nField
