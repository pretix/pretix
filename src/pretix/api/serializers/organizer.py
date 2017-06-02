from rest_framework import serializers

from pretix.base.models import Organizer


class OrganizerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organizer
        fields = ('name', 'slug')
