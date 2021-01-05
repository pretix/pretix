from collections import OrderedDict

from rest_framework import serializers


def remove_duplicates_from_list(data):
    return list(OrderedDict.fromkeys(data))


class ListMultipleChoiceField(serializers.MultipleChoiceField):
    def to_internal_value(self, data):
        if isinstance(data, str) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        internal_value_data = [
            super(serializers.MultipleChoiceField, self).to_internal_value(item)
            for item in data
        ]

        return remove_duplicates_from_list(internal_value_data)

    def to_representation(self, value):
        representation_data = [
            self.choice_strings_to_values.get(str(item), item) for item in value
        ]

        return remove_duplicates_from_list(representation_data)


class UploadedFileField(serializers.Field):
    default_error_messages = {
        'required': 'No file was submitted.',
        'not_found': 'The submitted file ID was not found.',
        'invalid_type': 'The submitted file has a file type that is not allowed in this field.',
        'size': 'The submitted file is too large to be used in this field.',
    }

    def __init__(self, *args, **kwargs):
        self.allowed_types = kwargs.pop('allowed_types', None)
        self.max_size = kwargs.pop('max_size', None)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        from pretix.base.models import CachedFile

        request = self.context.get('request', None)
        try:
            cf = CachedFile.objects.get(
                session_key=f'api-upload-{str(type(request.user or request.auth))}-{(request.user or request.auth).pk}',
                file__isnull=False,
                pk=data[len("file:"):],
            )
        except CachedFile.DoesNotExist:
            self.fail('not_found')

        if self.allowed_types and cf.type not in self.allowed_types:
            self.fail('invalid_type')
        if self.max_size and cf.file.size > self.max_size:
            self.fail('size')

        return cf.file

    def to_representation(self, value):
        if not value:
            return None

        try:
            url = value.url
        except AttributeError:
            return None
        request = self.context.get('request', None)
        if request is not None:
            return request.build_absolute_uri(url)
        return url
