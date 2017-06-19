from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Event


class EventSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Event
        fields = ('name', 'slug', 'live', 'currency', 'date_from',
                  'date_to', 'date_admission', 'is_public', 'presale_start',
                  'presale_end', 'location')
