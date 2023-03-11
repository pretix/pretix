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

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import OrderPositionSerializer
from pretix.api.serializers.organizer import GiftCardSerializer
from pretix.base.models import GiftCard, Order, ReusableMedium

logger = logging.getLogger(__name__)


class NestedOrderMiniSerializer(I18nAwareModelSerializer):
    event = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = Order
        fields = ['code', 'event']


class NestedOrderPositionSerializer(OrderPositionSerializer):
    order = NestedOrderMiniSerializer()


class NestedGiftCardSerializer(GiftCardSerializer):
    value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'),
                                     source='cached_value')


class ReusableMediaSerializer(I18nAwareModelSerializer):
    linked_orderposition = NestedOrderPositionSerializer(read_only=True)
    linked_giftcard = NestedGiftCardSerializer(read_only=True)

    def validate(self, data):
        data = super().validate(data)
        if '' in data:
            s = data['secret']
            qs = GiftCard.objects.filter(
                secret=s
            ).filter(
                Q(issuer=self.context["organizer"]) | Q(
                    issuer__gift_card_collector_acceptance__collector=self.context["organizer"])
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    {'secret': _(
                        'A gift card with the same secret already exists in your or an affiliated organizer account.')}
                )
        return data

    class Meta:
        model = ReusableMedium
        fields = (
            'id',
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
        )


class MediaLookupInputSerializer(serializers.Serializer):
    type = serializers.CharField(required=True)
    identifier = serializers.CharField(required=True)
