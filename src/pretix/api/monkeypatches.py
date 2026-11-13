import datetime

from django.db import models
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class CustomDateField(serializers.DateField):
    def to_internal_value(self, value):
        val = super().to_internal_value(value)
        if val < datetime.date(1900, 1, 1):
            raise ValidationError("Do not pass dates before 1900-01-01")
        return val


class CustomDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        val = super().to_internal_value(value)
        if val < datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc):
            raise ValidationError("Do not pass dates before 1900-01-01")
        return val


serializers.ModelSerializer.serializer_field_mapping.update({
    models.DateField: CustomDateField,
    models.DateTimeField: CustomDateTimeField,
})
