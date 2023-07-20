#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import logging
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import OrderPositionSerializer
from pretix.api.serializers.organizer import (
    CustomerSerializer, GiftCardSerializer,
)
from pretix.base.models import Order, OrderPosition, ReusableMedium

logger = logging.getLogger(__name__)


class NestedOrderMiniSerializer(I18nAwareModelSerializer):
    event = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = Order
        fields = ['code', 'event']


class NestedOrderPositionSerializer(OrderPositionSerializer):
    order = NestedOrderMiniSerializer()


class NestedGiftCardSerializer(GiftCardSerializer):

    def to_representation(self, instance):
        d = super().to_representation(instance)
        if hasattr(instance, 'cached_value'):
            d['value'] = str(Decimal(instance.cached_value).quantize(Decimal("0.01")))
        else:
            d['value'] = str(Decimal(instance.value).quantize(Decimal("0.01")))
        return d


class ReusableMediaSerializer(I18nAwareModelSerializer):
    organizer = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'linked_giftcard' in self.context['request'].query_params.getlist('expand'):
            self.fields['linked_giftcard'] = NestedGiftCardSerializer(read_only=True, context=self.context)
            if 'linked_giftcard.owner_ticket' in self.context['request'].query_params.getlist('expand'):
                self.fields['linked_giftcard'].fields['owner_ticket'] = NestedOrderPositionSerializer(read_only=True, context=self.context)
        else:
            self.fields['linked_giftcard'] = serializers.PrimaryKeyRelatedField(
                required=False,
                allow_null=True,
                queryset=self.context['organizer'].issued_gift_cards.all()
            )

        if 'linked_orderposition' in self.context['request'].query_params.getlist('expand'):
            self.fields['linked_orderposition'] = NestedOrderPositionSerializer(read_only=True)
        else:
            self.fields['linked_orderposition'] = serializers.PrimaryKeyRelatedField(
                required=False,
                allow_null=True,
                queryset=OrderPosition.all.filter(order__event__organizer=self.context['organizer']),
            )

        if 'customer' in self.context['request'].query_params.getlist('expand'):
            self.fields['customer'] = CustomerSerializer(read_only=True)
        else:
            self.fields['customer'] = serializers.SlugRelatedField(
                required=False,
                allow_null=True,
                slug_field='identifier',
                queryset=self.context['organizer'].customers.all()
            )

    def validate(self, data):
        data = super().validate(data)
        if 'type' in data and 'identifier' in data:
            qs = self.context['organizer'].reusable_media.filter(
                identifier=data['identifier'], type=data['type']
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    {'identifier': _('A medium with the same identifier and type already exists in your organizer account.')}
                )
        return data

    class Meta:
        model = ReusableMedium
        fields = (
            'id',
            'organizer',
            'created',
            'updated',
            'type',
            'identifier',
            'active',
            'expires',
            'customer',
            'linked_orderposition',
            'linked_giftcard',
            'info',
            'notes',
        )


class MediaLookupInputSerializer(serializers.Serializer):
    type = serializers.CharField(required=True)
    identifier = serializers.CharField(required=True)
