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
from collections import Counter
from typing import List

from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error

from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.cart import (
    CartPositionCreateSerializer, CartPositionSerializer,
)
from pretix.base.models import CartPosition
from pretix.base.services.cart import (
    _get_quota_availability, _get_voucher_availability, error_messages,
)
from pretix.base.services.locking import NoLockManager


class CartPositionViewSet(CreateModelMixin, DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CartPositionSerializer
    queryset = CartPosition.objects.none()
    filter_backends = (TotalOrderingFilter,)
    ordering = ('datetime',)
    ordering_fields = ('datetime', 'cart_id')
    lookup_field = 'id'
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    def get_queryset(self):
        return CartPosition.objects.filter(
            event=self.request.event,
            cart_id__endswith="@api"
        ).select_related('seat').prefetch_related('answers')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['quotas_for_item_cache'] = {}
        ctx['quotas_for_variation_cache'] = {}
        return ctx

    def create(self, request, *args, **kwargs):
        ctx = self.get_serializer_context()
        serializer = CartPositionCreateSerializer(data=request.data, context=ctx)
        serializer.is_valid(raise_exception=True)
        results = self._create(serializers=[serializer], raise_exception=True, ctx=ctx)
        headers = self.get_success_headers(serializer.data)
        return Response(results[0]['data'], status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['POST'])
    def bulk_create(self, request, *args, **kwargs):
        if not isinstance(request.data, list):  # noqa
            return Response({"error": "Please supply a list"}, status=status.HTTP_400_BAD_REQUEST)

        ctx = self.get_serializer_context()
        serializers = [
            CartPositionCreateSerializer(data=d, context=ctx)
            for d in request.data
        ]

        results = self._create(serializers=serializers, raise_exception=False, ctx=ctx)
        return Response({'results': results}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        raise NotImplementedError()

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.addons.all().delete()
        instance.delete()

    def _require_locking(self, quota_diff, voucher_use_diff, seat_diff):
        if voucher_use_diff or seat_diff:
            # If any vouchers or seats are used, we lock to make sure we don't redeem them to often
            return True

        if quota_diff and any(q.size is not None for q in quota_diff):
            # If any quotas are affected that are not unlimited, we lock
            return True

        return False

    @cached_property
    def _create_default_cart_id(self):
        cid = "{}@api".format(get_random_string(48))
        while CartPosition.objects.filter(cart_id=cid).exists():
            cid = "{}@api".format(get_random_string(48))
        return cid

    def _create(self, serializers: List[CartPositionCreateSerializer], ctx, raise_exception=False):
        voucher_use_diff = Counter()
        quota_diff = Counter()
        seat_diff = Counter()
        results = [{} for pserializer in serializers]

        for i, pserializer in enumerate(serializers):
            if not pserializer.is_valid(raise_exception=raise_exception):
                results[i] = {
                    'success': False,
                    'data': None,
                    'errors': pserializer.errors,
                }

        for pserializer in serializers:
            if pserializer.errors:
                continue

            validated_data = pserializer.validated_data
            if not validated_data.get('cart_id'):
                validated_data['cart_id'] = self._create_default_cart_id

            if validated_data.get('voucher'):
                voucher_use_diff[validated_data['voucher']] += 1

            if validated_data.get('seat'):
                seat_diff[validated_data['seat']] += 1

            for q in validated_data['_quotas']:
                quota_diff[q] += 1
            for sub_data in validated_data.get('addons', []) + validated_data.get('bundled', []):
                for q in sub_data['_quotas']:
                    quota_diff[q] += 1

        seats_seen = set()

        lockfn = NoLockManager
        if self._require_locking(quota_diff, voucher_use_diff, seat_diff):
            lockfn = self.request.event.lock

        with lockfn() as now_dt, transaction.atomic():
            vouchers_ok, vouchers_depend_on_cart = _get_voucher_availability(
                self.request.event,
                voucher_use_diff,
                now_dt,
                exclude_position_ids=[],
            )
            quotas_ok = _get_quota_availability(quota_diff, now_dt)

            for i, pserializer in enumerate(serializers):
                if results[i]:
                    continue

                try:
                    validated_data = pserializer.validated_data

                    if validated_data.get('seat'):
                        # Assumption: Add-ons currently can't have seats
                        if validated_data['seat'] in seats_seen:
                            raise ValidationError(error_messages['seat_multiple'])
                        seats_seen.add(validated_data['seat'])

                    quotas_needed = Counter()
                    for q in validated_data['_quotas']:
                        quotas_needed[q] += 1
                    for sub_data in validated_data.get('addons', []) + validated_data.get('bundled', []):
                        for q in sub_data['_quotas']:
                            quotas_needed[q] += 1

                    for q, needed in quotas_needed.items():
                        if quotas_ok[q] < needed:
                            raise ValidationError(
                                _('There is not enough quota available on quota "{}" to perform the operation.').format(
                                    q.name
                                )
                            )

                    if validated_data.get('voucher'):
                        # Assumption: Add-ons currently can't have vouchers, thus we only need to check the main voucher
                        if vouchers_ok[validated_data['voucher']] < 1:
                            raise ValidationError(
                                {'voucher': [_('The specified voucher has already been used the maximum number of times.')]}
                            )

                    if validated_data.get('seat'):
                        # Assumption: Add-ons currently can't have seats, thus we only need to check the main product
                        if not validated_data['seat'].is_available(
                            sales_channel=validated_data.get('sales_channel', 'web'),
                            distance_ignore_cart_id=validated_data['cart_id'],
                            ignore_voucher_id=validated_data['voucher'].pk if validated_data.get('voucher') else None,
                        ):
                            raise ValidationError(
                                {'seat': [_('The selected seat "{seat}" is not available.').format(seat=validated_data['seat'].name)]}
                            )

                    for q, needed in quotas_needed.items():
                        quotas_ok[q] -= needed
                    if validated_data.get('voucher'):
                        vouchers_ok[validated_data['voucher']] -= 1

                    if any(qa < 0 for qa in quotas_ok.values()):
                        # Safeguard, should never happen because of conditions above
                        raise ValidationError(error_messages['unavailable'])

                    cp = pserializer.create(validated_data)

                    d = CartPositionSerializer(cp, context=ctx).data
                    addons = sorted(cp.addons.all(), key=lambda a: a.pk)  # order of creation, safe since they are created in the same transaction
                    d['addons'] = CartPositionSerializer([a for a in addons if not a.is_bundled], many=True, context=ctx).data
                    d['bundled'] = CartPositionSerializer([a for a in addons if a.is_bundled], many=True, context=ctx).data

                    results[i] = {
                        'success': True,
                        'data': d,
                        'errors': None,
                    }
                except ValidationError as e:
                    if raise_exception:
                        raise
                    results[i] = {
                        'success': False,
                        'data': None,
                        'errors': as_serializer_error(e),
                    }

        return results
