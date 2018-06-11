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
        )

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
