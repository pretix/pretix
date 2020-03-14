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
