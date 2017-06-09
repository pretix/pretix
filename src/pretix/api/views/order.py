import django_filters
from django.http import FileResponse
from rest_framework import filters, viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import APIException

from pretix.api.filters.ordering import ExplicitOrderingFilter
from pretix.api.serializers.order import InvoiceSerializer, OrderSerializer
from pretix.base.models import Invoice, Order
from pretix.base.services.invoices import invoice_pdf


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

    def get_queryset(self):
        return self.request.event.orders.prefetch_related('positions').select_related('invoice_address')


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
