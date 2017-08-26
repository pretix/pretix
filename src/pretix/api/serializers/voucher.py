from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Voucher


class VoucherSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Voucher
        fields = ('id', 'code', 'max_usages', 'redeemed', 'valid_until', 'block_quota',
                  'allow_ignore_quota', 'price_mode', 'value', 'item', 'variation', 'quota',
                  'tag', 'comment', 'subevent')
