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
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.response import Response

from pretix.api.serializers.cart import (
    CartPositionCreateSerializer, CartPositionSerializer,
)
from pretix.base.models import CartPosition


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
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = CartPositionCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            cp = serializer.instance
            serializer = CartPositionSerializer(cp, context=serializer.context)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()
