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
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.response import Response
from rest_framework.settings import api_settings

from pretix.api.serializers.cart import (
    CartPositionCreateSerializer, CartPositionSerializer,
)
from pretix.base.models import CartPosition
from pretix.base.services.locking import NoLockManager


class CartPositionViewSet(CreateModelMixin, DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CartPositionSerializer
    queryset = CartPosition.objects.none()
    filter_backends = (OrderingFilter,)
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
        ctx['quota_cache'] = {}
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = CartPositionCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(), self.request.event.lock():
            self.perform_create(serializer)
        cp = serializer.instance
        serializer = CartPositionSerializer(cp, context=serializer.context)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['POST'])
    def bulk_create(self, request, *args, **kwargs):
        if not isinstance(request.data, list):  # noqa
            return Response({"error": "Please supply a list"}, status=status.HTTP_400_BAD_REQUEST)

        ctx = self.get_serializer_context()
        with transaction.atomic():
            serializers = [
                CartPositionCreateSerializer(data=d, context=ctx)
                for d in request.data
            ]

            lockfn = self.request.event.lock
            if not any(s.is_valid(raise_exception=False) for s in serializers):
                lockfn = NoLockManager

            results = []
            with lockfn():
                for s in serializers:
                    if s.is_valid(raise_exception=False):
                        try:
                            cp = s.save()
                        except ValidationError as e:
                            results.append({
                                'success': False,
                                'data': None,
                                'errors': {api_settings.NON_FIELD_ERRORS_KEY: e.detail},
                            })
                        else:
                            results.append({
                                'success': True,
                                'data': CartPositionSerializer(cp, context=ctx).data,
                                'errors': None,
                            })
                    else:
                        results.append({
                            'success': False,
                            'data': None,
                            'errors': s.errors,
                        })

        return Response({'results': results}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save()
