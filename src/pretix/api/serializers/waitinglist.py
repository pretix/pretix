from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import WaitingListEntry


class WaitingListSerializer(I18nAwareModelSerializer):

    class Meta:
        model = WaitingListEntry
        fields = ('id', 'created', 'email', 'voucher', 'item', 'variation', 'locale', 'subevent')
