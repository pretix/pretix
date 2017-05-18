from rest_framework import serializers

from pretix.base.models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ('name', 'slug')
