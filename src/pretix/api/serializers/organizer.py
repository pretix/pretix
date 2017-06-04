from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Organizer


class OrganizerSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Organizer
        fields = ('name', 'slug')
