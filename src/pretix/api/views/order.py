import django_filters
from django.http import FileResponse
from rest_framework import filters, viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from pretix.api.filters.ordering import ExplicitOrderingFilter
from pretix.api.serializers.order import (
    InvoiceSerializer, OrderPositionSerializer, OrderSerializer,
)
from pretix.base.models import Invoice, Order, OrderPosition
from pretix.base.services.invoices import invoice_pdf
from pretix.base.services.tickets import (
    get_cachedticket_for_order, get_cachedticket_for_position,
)
from pretix.base.signals import register_ticket_outputs


class OrderFilter(filters.FilterSet):
    class Meta:
        model = Order
        fields = ['code', 'status', 'email', 'locale']


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.none()
    filter_backends = (filters.DjangoFilterBackend, ExplicitOrderingFilter)
    ordering = ('datetime',)
    ordering_fields = ('datetime', 'code', 'status')
    filter_class = OrderFilter
    lookup_field = 'code'

    def get_queryset(self):
        return self.request.event.orders.prefetch_related(
            'positions', 'positions__checkins', 'positions__item',
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


class OrderPositionFilter(filters.FilterSet):
    order = django_filters.CharFilter(name='order', lookup_expr='code')
    has_checkin = django_filters.rest_framework.BooleanFilter(method='has_checkin_qs')

    def has_checkin_qs(self, queryset, name, value):
        print(value)
        return queryset.filter(checkins__isnull=not value)

    class Meta:
        model = OrderPosition
        fields = ['item', 'variation', 'attendee_name', 'secret', 'order', 'order__status', 'has_checkin']


class OrderPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.objects.none()
    filter_backends = (filters.DjangoFilterBackend, ExplicitOrderingFilter)
    ordering = ('order__datetime', 'positionid')
    ordering_fields = ('order__code', 'order__datetime', 'positionid', 'attendee_name', 'order__status',)
    filter_class = OrderPositionFilter

    def get_queryset(self):
        return OrderPosition.objects.filter(order__event=self.request.event).prefetch_related(
            'checkins',
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


class InvoiceFilter(filters.FilterSet):
    refers = django_filters.CharFilter(name='refers', lookup_expr='invoice_no__iexact')
    order = django_filters.CharFilter(name='order', lookup_expr='code__iexact')

    class Meta:
        model = Invoice
        fields = ['order', 'invoice_no', 'is_cancellation', 'refers', 'locale']


class RetryException(APIException):
    status_code = 409
    default_detail = 'The requested resource is not ready, please retry later.'
    default_code = 'retry_later'


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.none()
    filter_backends = (filters.DjangoFilterBackend, ExplicitOrderingFilter)
    ordering = ('invoice_no',)
    ordering_fields = ('invoice_no', 'date')
    filter_class = InvoiceFilter
    lookup_field = 'invoice_no'
    lookup_url_kwarg = 'invoice_no'

    def get_queryset(self):
        return self.request.event.invoices.prefetch_related('lines').select_related('order')

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
