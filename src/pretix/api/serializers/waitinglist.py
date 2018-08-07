from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import WaitingListEntry


class WaitingListSerializer(I18nAwareModelSerializer):

    class Meta:
        model = WaitingListEntry
        fields = ('id', 'created', 'email', 'voucher', 'item', 'variation', 'locale', 'subevent', 'priority')
        read_only_fields = ('id', 'created', 'voucher')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        WaitingListEntry.clean_duplicate(full_data.get('email'), full_data.get('item'), full_data.get('variation'),
                                         full_data.get('subevent'), self.instance.pk if self.instance else None)
        WaitingListEntry.clean_itemvar(event, full_data.get('item'), full_data.get('variation'))
        WaitingListEntry.clean_subevent(event, full_data.get('subevent'))

        if 'item' in data or 'variation' in data:
            availability = (
                full_data.get('variation').check_quotas(count_waitinglist=True, subevent=full_data.get('subevent'))
                if full_data.get('variation')
                else full_data.get('item').check_quotas(count_waitinglist=True, subevent=full_data.get('subevent'))
            )
            if availability[0] == 100:
                raise ValidationError("This product is currently available.")

        return data
