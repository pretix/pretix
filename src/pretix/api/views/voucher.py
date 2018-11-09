import contextlib
from django.db import transaction
from django.db.models import F, Q
from django.utils.timezone import now
from django_filters.rest_framework import (
    BooleanFilter, DjangoFilterBackend, FilterSet,
)
from rest_framework import viewsets, status
from rest_framework.decorators import list_route
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

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


class VoucherViewSet(viewsets.ModelViewSet):
    serializer_class = VoucherSerializer
    queryset = Voucher.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('id',)
    ordering_fields = ('id', 'code', 'max_usages', 'valid_until', 'value')
    filterset_class = VoucherFilter
    permission = 'can_view_vouchers'
    write_permission = 'can_change_vouchers'

    def get_queryset(self):
        return self.request.event.vouchers.all()

    def _predict_quota_check(self, data, instance):
        # This method predicts if Voucher.clean_quota_needs_checking
        # *migh* later require a quota check. It is only approximate
        # and returns True a little too often. The point is to avoid
        # locks when we know we won't need them.
        if 'allow_ignore_quota' in data and data.get('allow_ignore_quota'):
            return False
        if instance and 'allow_ignore_quota' not in data and instance.allow_ignore_quota:
            return False

        if 'block_quota' in data and not data.get('block_quota'):
           return False
        if instance and 'block_quota' not in data and not instance.block_quota:
            return False

        return True

    def create(self, request, *args, **kwargs):
        if self._predict_quota_check(request.data, None):
            lockfn = request.event.lock
        else:
            lockfn = contextlib.suppress  # noop context manager
        with lockfn():
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

    def update(self, request, *args, **kwargs):
        if self._predict_quota_check(request.data, self.get_object()):
            lockfn = request.event.lock
        else:
            lockfn = contextlib.suppress  # noop context manager
        with lockfn():
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
        super().perform_destroy(instance)
