from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import Voucher


class VoucherSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Voucher
        fields = ('id', 'code', 'max_usages', 'redeemed', 'valid_until', 'block_quota',
                  'allow_ignore_quota', 'price_mode', 'value', 'item', 'variation', 'quota',
                  'tag', 'comment', 'subevent')
        read_only_fields = ('id', 'redeemed')

    def validate(self, data):
        data = super().validate(data)

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        Voucher.clean_item_properties(
            full_data, self.context.get('event'),
            full_data.get('quota'), full_data.get('item'), full_data.get('variation')
        )
        Voucher.clean_subevent(
            full_data, self.context.get('event')
        )
        Voucher.clean_max_usages(full_data, self.instance.redeemed if self.instance else 0)
        check_quota = Voucher.clean_quota_needs_checking(
            full_data, self.instance,
            item_changed=self.instance and (
                full_data.get('item') != self.instance.item or
                full_data.get('variation') != self.instance.variation or
                full_data.get('quota') != self.instance.quota
            ),
            creating=not self.instance
        )
        if check_quota:
            Voucher.clean_quota_check(
                full_data, 1, self.instance, self.context.get('event'),
                full_data.get('quota'), full_data.get('item'), full_data.get('variation')
            )
        Voucher.clean_voucher_code(full_data, self.context.get('event'), self.instance.pk if self.instance else None)

        return data
