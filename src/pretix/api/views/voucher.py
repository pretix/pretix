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

from decimal import Decimal

from django.db import models, transaction
from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from django_filters.rest_framework import (
    BooleanFilter, CharFilter, DjangoFilterBackend, FilterSet,
)
from django_scopes import scopes_disabled
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.voucher import VoucherSerializer
from pretix.base.models import Order, OrderPosition, Voucher

with scopes_disabled():
    class VoucherFilter(FilterSet):
        active = BooleanFilter(method='filter_active')
        code = CharFilter(lookup_expr='iexact')

        class Meta:
            model = Voucher
            fields = ['code', 'max_usages', 'redeemed', 'block_quota', 'allow_ignore_quota',
                      'price_mode', 'value', 'item', 'variation', 'quota', 'tag', 'subevent']

        def filter_active(self, queryset, name, value):
            if value:
                return queryset.filter(Q(redeemed__lt=F('max_usages')) &
                                       (Q(valid_until__isnull=True) | Q(valid_until__gt=now())))
            else:
                return queryset.filter(Q(redeemed__gte=F('max_usages')) |
                                       (Q(valid_until__isnull=False) & Q(valid_until__lte=now())))


class VoucherViewSet(viewsets.ModelViewSet):
    serializer_class = VoucherSerializer
    queryset = Voucher.objects.none()
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    ordering = ('id',)
    ordering_fields = ('id', 'code', 'max_usages', 'valid_until', 'value')
    filterset_class = VoucherFilter
    permission = 'can_view_vouchers'
    write_permission = 'can_change_vouchers'

    @scopes_disabled()  # we have an event check here, and we can save some performance on subqueries
    def get_queryset(self):
        opq = OrderPosition.objects.filter(
            voucher_id=OuterRef('pk'),
            voucher_budget_use__isnull=False,
            order__status__in=[
                Order.STATUS_PAID,
                Order.STATUS_PENDING
            ]
        ).order_by().values('voucher_id').annotate(s=Sum('voucher_budget_use')).values('s')

        return self.request.event.vouchers.annotate(
            budget_used=Coalesce(Subquery(opq, output_field=models.DecimalField(max_digits=13, decimal_places=2)), Decimal('0.00'))
        ).select_related(
            'item', 'quota', 'seat', 'variation'
        )

    @transaction.atomic()
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.voucher.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    @transaction.atomic()
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.voucher.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied('This voucher can not be deleted as it has already been used.')

        instance.log_action(
            'pretix.voucher.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        with transaction.atomic():
            instance.cartposition_set.filter(addon_to__isnull=False).delete()
            instance.cartposition_set.all().delete()
            super().perform_destroy(instance)

    @action(detail=False, methods=['POST'])
    @transaction.atomic()
    def batch_create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save(event=self.request.event)
            for i, v in enumerate(serializer.instance):
                v.log_action(
                    'pretix.voucher.added',
                    user=self.request.user,
                    auth=self.request.auth,
                    data=self.request.data[i]
                )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
