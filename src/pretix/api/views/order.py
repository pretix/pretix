import datetime

import django_filters
import pytz
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import FileResponse
from django.utils.timezone import make_aware
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pretix.api.serializers.order import (
    InvoiceSerializer, OrderPositionSerializer, OrderSerializer,
)
from pretix.base.models import Invoice, Order, OrderPosition, Quota
from pretix.base.models.organizer import TeamAPIToken
from pretix.base.services.invoices import invoice_pdf
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import (
    OrderError, cancel_order, extend_order, mark_order_expired,
    mark_order_paid,
)
from pretix.base.services.tickets import (
    get_cachedticket_for_order, get_cachedticket_for_position,
)
from pretix.base.signals import register_ticket_outputs


class OrderFilter(FilterSet):
    class Meta:
        model = Order
        fields = ['code', 'status', 'email', 'locale']


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('datetime',)
    ordering_fields = ('datetime', 'code', 'status')
    filter_class = OrderFilter
    lookup_field = 'code'
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    def get_queryset(self):
        return self.request.event.orders.prefetch_related(
            'positions', 'positions__checkins', 'positions__item', 'positions__answers', 'positions__answers__options',
            'fees'
        ).select_related(
            'invoice_address'
        )

    def _get_output_provider(self, identifier):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            prov = response(self.request.event)
            if prov.identifier == identifier:
                return prov
        raise NotFound('Unknown output provider.')

    @detail_route(url_name='download', url_path='download/(?P<output>[^/]+)')
    def download(self, request, output, **kwargs):
        provider = self._get_output_provider(output)
        order = self.get_object()

        if order.status != Order.STATUS_PAID:
            raise PermissionDenied("Downloads are not available for unpaid orders.")

        ct = get_cachedticket_for_order(order, provider.identifier)

        if not ct.file:
            raise RetryException()
        else:
            resp = FileResponse(ct.file.file, content_type=ct.type)
            resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}{}"'.format(
                self.request.event.slug.upper(), order.code,
                provider.identifier, ct.extension
            )
            return resp

    @detail_route(methods=['POST'])
    def mark_paid(self, request, **kwargs):
        order = self.get_object()

        if order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            try:
                mark_order_paid(
                    order, manual=True,
                    user=request.user if request.user.is_authenticated else None,
                    api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
                )
            except Quota.QuotaExceededException as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except SendMailException:
                pass

            return self.retrieve(request, [], **kwargs)
        return Response(
            {'detail': 'The order is not pending or expired.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @detail_route(methods=['POST'])
    def mark_canceled(self, request, **kwargs):
        send_mail = request.data.get('send_email', True)

        order = self.get_object()
        if not order.cancel_allowed():
            return Response(
                {'detail': 'The order is not allowed to be canceled.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cancel_order(
            order,
            user=request.user if request.user.is_authenticated else None,
            api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
            send_mail=send_mail
        )
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def mark_pending(self, request, **kwargs):
        order = self.get_object()

        if order.status != Order.STATUS_PAID:
            return Response(
                {'detail': 'The order is not paid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = Order.STATUS_PENDING
        order.payment_manual = True
        order.save()
        order.log_action(
            'pretix.event.order.unpaid',
            user=request.user if request.user.is_authenticated else None,
            api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
        )
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def mark_expired(self, request, **kwargs):
        order = self.get_object()

        if order.status != Order.STATUS_PENDING:
            return Response(
                {'detail': 'The order is not pending.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        mark_order_expired(
            order,
            user=request.user if request.user.is_authenticated else None,
            api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
        )
        return self.retrieve(request, [], **kwargs)

    # TODO: Find a way to implement mark_refunded

    @detail_route(methods=['POST'])
    def extend(self, request, **kwargs):
        new_date = request.data.get('expires', None)
        force = request.data.get('force', False)
        if not new_date:
            return Response(
                {'detail': 'New date is missing.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        df = serializers.DateField()
        try:
            new_date = df.to_internal_value(new_date)
        except:
            return Response(
                {'detail': 'New date is invalid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tz = pytz.timezone(self.request.event.settings.timezone)
        new_date = make_aware(datetime.datetime.combine(
            new_date,
            datetime.time(hour=23, minute=59, second=59)
        ), tz)

        order = self.get_object()

        try:
            extend_order(
                order,
                new_date=new_date,
                force=force,
                user=request.user if request.user.is_authenticated else None,
                api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
            )
            return self.retrieve(request, [], **kwargs)
        except OrderError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class OrderPositionFilter(FilterSet):
    order = django_filters.CharFilter(name='order', lookup_expr='code')
    has_checkin = django_filters.rest_framework.BooleanFilter(method='has_checkin_qs')
    attendee_name = django_filters.CharFilter(method='attendee_name_qs')

    def has_checkin_qs(self, queryset, name, value):
        return queryset.filter(checkins__isnull=not value)

    def attendee_name_qs(self, queryset, name, value):
        return queryset.filter(Q(attendee_name=value) | Q(addon_to__attendee_name=value))

    class Meta:
        model = OrderPosition
        fields = ['item', 'variation', 'attendee_name', 'secret', 'order', 'order__status', 'has_checkin',
                  'addon_to', 'subevent']


class OrderPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('order__datetime', 'positionid')
    ordering_fields = ('order__code', 'order__datetime', 'positionid', 'attendee_name', 'order__status',)
    filter_class = OrderPositionFilter
    permission = 'can_view_orders'

    def get_queryset(self):
        return OrderPosition.objects.filter(order__event=self.request.event).prefetch_related(
            'checkins', 'answers', 'answers__options'
        ).select_related(
            'item', 'order', 'order__event', 'order__event__organizer'
        )

    def _get_output_provider(self, identifier):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            prov = response(self.request.event)
            if prov.identifier == identifier:
                return prov
        raise NotFound('Unknown output provider.')

    @detail_route(url_name='download', url_path='download/(?P<output>[^/]+)')
    def download(self, request, output, **kwargs):
        provider = self._get_output_provider(output)
        pos = self.get_object()

        if pos.order.status != Order.STATUS_PAID:
            raise PermissionDenied("Downloads are not available for unpaid orders.")
        if pos.addon_to_id and not request.event.settings.ticket_download_addons:
            raise PermissionDenied("Downloads are not enabled for add-on products.")
        if not pos.item.admission and not request.event.settings.ticket_download_nonadm:
            raise PermissionDenied("Downloads are not enabled for non-admission products.")

        ct = get_cachedticket_for_position(pos, provider.identifier)

        if not ct.file:
            raise RetryException()
        else:
            resp = FileResponse(ct.file.file, content_type=ct.type)
            resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}-{}{}"'.format(
                self.request.event.slug.upper(), pos.order.code, pos.positionid,
                provider.identifier, ct.extension
            )
            return resp


class InvoiceFilter(FilterSet):
    refers = django_filters.CharFilter(method='refers_qs')
    number = django_filters.CharFilter(method='nr_qs')
    order = django_filters.CharFilter(name='order', lookup_expr='code__iexact')

    def refers_qs(self, queryset, name, value):
        return queryset.annotate(
            refers_nr=Concat('refers__prefix', 'refers__invoice_no')
        ).filter(refers_nr__iexact=value)

    def nr_qs(self, queryset, name, value):
        return queryset.filter(nr__iexact=value)

    class Meta:
        model = Invoice
        fields = ['order', 'number', 'is_cancellation', 'refers', 'locale']


class RetryException(APIException):
    status_code = 409
    default_detail = 'The requested resource is not ready, please retry later.'
    default_code = 'retry_later'


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('nr',)
    ordering_fields = ('nr', 'date')
    filter_class = InvoiceFilter
    permission = 'can_view_orders'
    lookup_url_kwarg = 'number'
    lookup_field = 'nr'

    def get_queryset(self):
        return self.request.event.invoices.prefetch_related('lines').select_related('order', 'refers').annotate(
            nr=Concat('prefix', 'invoice_no')
        )

    @detail_route()
    def download(self, request, **kwargs):
        invoice = self.get_object()

        if not invoice.file:
            invoice_pdf(invoice.pk)
            invoice.refresh_from_db()

        if not invoice.file:
            raise RetryException()

        resp = FileResponse(invoice.file.file, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(invoice.number)
        return resp
