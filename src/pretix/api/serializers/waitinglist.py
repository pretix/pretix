from rest_framework import serializers

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import WaitingListEntry


class WaitingListSerializer(I18nAwareModelSerializer):
    voucher = serializers.SlugRelatedField(slug_field='code', read_only=True)

    class Meta:
        model = WaitingListEntry
        fields = ('id', 'created', 'email', 'voucher', 'item', 'variation', 'locale')
