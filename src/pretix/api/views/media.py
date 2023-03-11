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
from decimal import Decimal

import django_filters
from django.db import transaction
from django.db.models import OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pretix.api.serializers.media import ReusableMediaSerializer, MediaLookupInputSerializer
from pretix.base.models import (
    Checkin, GiftCard, GiftCardTransaction, OrderPosition, ReusableMedium,
)
from pretix.helpers import OF_SELF
from pretix.helpers.dicts import merge_dicts

with scopes_disabled():
    class ReusableMediumFilter(FilterSet):
        identifier = django_filters.CharFilter(field_name='identifier')
        type = django_filters.CharFilter(field_name='type')
        customer = django_filters.CharFilter(field_name='customer__identifier')

        class Meta:
            model = ReusableMedium
            fields = ['identifier', 'type', 'active', 'customer', 'linked_orderposition', 'linked_giftcard']


class ReusableMediaViewSet(viewsets.ModelViewSet):
    serializer_class = ReusableMediaSerializer
    queryset = ReusableMedium.objects.none()
    permission = 'can_manage_reusable_media'
    write_permission = 'can_manage_reusable_media'
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('-updated', '-id')
    ordering_fields = ('created', 'updated', 'identifier', 'type', 'id')
    filterset_class = ReusableMediumFilter

    def get_queryset(self):
        s = GiftCardTransaction.objects.filter(
            card=OuterRef('pk')
        ).order_by().values('card').annotate(s=Sum('value')).values('s')
        return self.request.organizer.reusable_media.prefetch_related(
            Prefetch(
                'linked_orderposition',
                queryset=OrderPosition.objects.select_related(
                    'order', 'order__event', 'order__event__organizer', 'seat',
                ).prefetch_related(
                    Prefetch('checkins', queryset=Checkin.objects.all()),
                    'answers', 'answers__options', 'answers__question',
                )
            ),
            Prefetch(
                'linked_giftcard',
                queryset=GiftCard.objects.annotate(
                    cached_value=Coalesce(Subquery(s), Decimal('0.00'))
                )
            )
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        value = serializer.validated_data.pop('value')
        inst = serializer.save(issuer=self.request.organizer)
        inst.transactions.create(value=value)
        inst.log_action(
            'pretix.reusable_medium.created',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        ReusableMedium.objects.select_for_update(of=OF_SELF).get(pk=self.get_object().pk)
        inst = serializer.save(secret=serializer.instance.secret, currency=serializer.instance.currency,
                               testmode=serializer.instance.testmode)
        inst.log_action(
            'pretix.reusable_medium.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst

    def perform_destroy(self, instance):
        raise MethodNotAllowed("Media cannot be deleted.")

    @action(methods=["POST"], detail=False)
    def lookup(self, request, *args, **kwargs):
        s = MediaLookupInputSerializer(
            data=request.data,
        )
        s.is_valid(raise_exception=True)

        try:
            m = ReusableMedium.objects.get(
                type=s.validated_data["type"],
                identifier=s.validated_data["identifier"],
                organizer=request.organizer,
            )
            s = self.get_serializer(m)
            return Response({"result": s.data})
        except ReusableMedium.DoesNotExist:
            return Response({"result": None})
