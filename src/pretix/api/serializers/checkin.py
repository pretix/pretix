from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.channels import get_all_sales_channels
from pretix.base.models import CheckinList


class CheckinListSerializer(I18nAwareModelSerializer):
    checkin_count = serializers.IntegerField(read_only=True)
    position_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CheckinList
        fields = ('id', 'name', 'all_products', 'limit_products', 'subevent', 'checkin_count', 'position_count',
                  'include_pending', 'auto_checkin_sales_channels', 'allow_multiple_entries')

    def validate(self, data):
        data = super().validate(data)
        event = self.context['event']

        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)

        for item in full_data.get('limit_products'):
            if event != item.event:
                raise ValidationError(_('One or more items do not belong to this event.'))

        if event.has_subevents:
            if full_data.get('subevent') and event != full_data.get('subevent').event:
                raise ValidationError(_('The subevent does not belong to this event.'))
        else:
            if full_data.get('subevent'):
                raise ValidationError(_('The subevent does not belong to this event.'))

        for channel in full_data.get('auto_checkin_sales_channels') or []:
            if channel not in get_all_sales_channels():
                raise ValidationError(_('Unknown sales channel.'))

        return data
