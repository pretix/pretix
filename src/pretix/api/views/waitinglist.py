import django_filters
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pretix.api.serializers.waitinglist import WaitingListSerializer
from pretix.base.models import TeamAPIToken, WaitingListEntry
from pretix.base.models.waitinglist import WaitingListException


class WaitingListFilter(FilterSet):
    has_voucher = django_filters.rest_framework.BooleanFilter(method='has_voucher_qs')

    def has_voucher_qs(self, queryset, name, value):
        return queryset.filter(voucher__isnull=not value)

    class Meta:
        model = WaitingListEntry
        fields = ['item', 'variation', 'email', 'locale', 'has_voucher', 'subevent']


class WaitingListViewSet(viewsets.ModelViewSet):
    serializer_class = WaitingListSerializer
    queryset = WaitingListEntry.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('created',)
    ordering_fields = ('id', 'created', 'email', 'item')
    filter_class = WaitingListFilter
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    def get_queryset(self):
        return self.request.event.waitinglistentries.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.orders.waitinglist.added',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
        )

    def perform_update(self, serializer):
        if serializer.instance.voucher:
            raise PermissionDenied('This entry can not be changed as it has already been assigned a voucher.')
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.orders.waitinglist.changed',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
        )

    def perform_destroy(self, instance):
        if instance.voucher:
            raise PermissionDenied('This entry can not be deleted as it has already been assigned a voucher.')

        instance.log_action(
            'pretix.event.orders.waitinglist.deleted',
            user=self.request.user,
            api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
        )
        super().perform_destroy(instance)

    @detail_route(methods=['POST'])
    def send_voucher(self, *args, **kwargs):
        try:
            self.get_object().send_voucher(
                user=self.request.user,
                api_token=(self.request.auth if isinstance(self.request.auth, TeamAPIToken) else None),
            )
        except WaitingListException as e:
            raise ValidationError(str(e))
        else:
            return Response(status=204)
