#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

        expand_nested = self.context['request'].query_params.getlist('expand')

        if 'linked_giftcard' in expand_nested:
            self.fields['linked_giftcard'] = NestedGiftCardSerializer(read_only=True, context=self.context)
            if 'linked_giftcard.owner_ticket' in expand_nested:
                self.fields['linked_giftcard'].fields['owner_ticket'] = NestedOrderPositionSerializer(read_only=True, context=self.context)
        else:
            self.fields['linked_giftcard'] = serializers.PrimaryKeyRelatedField(
                required=False,
                allow_null=True,
                queryset=self.context['organizer'].issued_gift_cards.all()
            )

        # keep linked_orderposition (singular) for backwards compatibility, will be overwritten in self.validate
        self.fields['linked_orderposition'] = serializers.PrimaryKeyRelatedField(
            required=False,
            allow_null=True,
            queryset=OrderPosition.all.filter(order__event__organizer=self.context['organizer']),
        )

        if 'linked_orderposition' in expand_nested or 'linked_orderpositions' in expand_nested:
            self.fields['linked_orderpositions'] = NestedOrderPositionSerializer(
                many=True,
                read_only=True
            )
        else:
            self.fields['linked_orderpositions'] = serializers.PrimaryKeyRelatedField(
                many=True,
                required=False,
                allow_null=True,
                queryset=OrderPosition.all.filter(order__event__organizer=self.context['organizer']),
            )

        if 'customer' in expand_nested:
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
        if 'linked_orderposition' in data:
            linked_orderposition = data['linked_orderposition']
            # backwards-compatibility
            if 'linked_orderpositions' in data:
                raise ValidationError({
                    'linked_orderposition': _('You cannot use linked_orderposition and linked_orderpositions at the same time.')
                })
            if self.instance.linked_orderpositions.count() > 1:
                raise ValidationError({
                    'linked_orderposition': _('There are more than one linked_orderposition. You need to use linked_orderpositions.')
                })

            data['linked_orderpositions'] = [linked_orderposition] if linked_orderposition else []

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

    def to_representation(self, obj):
        r = super(ReusableMediaSerializer, self).to_representation(obj)
        ops = r.get('linked_orderpositions')
        if len(ops) < 2:
            # add linked_orderposition (singular) for backwards compatibility
            r['linked_orderposition'] = ops[0] if ops else None
        return r

    class Meta:
        model = ReusableMedium
        fields = (
            'id',
            'organizer',
            'created',
            'updated',
            'type',
            'identifier',
            'secret',
            'label',
            'active',
            'expires',
            'customer',
            'linked_orderpositions',
            'linked_giftcard',
            'info',
            'notes',
        )


class MediaLookupInputSerializer(serializers.Serializer):
    type = serializers.CharField(required=True)
    identifier = serializers.CharField(required=True)
