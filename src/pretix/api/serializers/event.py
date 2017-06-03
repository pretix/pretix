from rest_framework import serializers

from pretix.base.models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location')
