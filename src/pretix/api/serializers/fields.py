from rest_framework import serializers


class ListMultipleChoiceField(serializers.MultipleChoiceField):
    def to_internal_value(self, data):
        return list(super().to_internal_value(data))
