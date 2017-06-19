from django.db.models import F, Q
from django.utils.timezone import now
from django_filters.rest_framework import (
    BooleanFilter, DjangoFilterBackend, FilterSet,
)
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from pretix.api.serializers.voucher import VoucherSerializer
from pretix.base.models import Voucher


class VoucherFilter(FilterSet):
    active = BooleanFilter(method='filter_active')

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


class VoucherViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VoucherSerializer
    queryset = Voucher.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('id',)
    ordering_fields = ('id', 'code', 'max_usages', 'valid_until', 'value')
    filter_class = VoucherFilter
    permission = 'can_view_vouchers'

    def get_queryset(self):
        return self.request.event.vouchers.all()
