import datetime

import django_filters
import pytz
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.timezone import make_aware, now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.exceptions import (
    APIException, NotFound, PermissionDenied, ValidationError,
)
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

from pretix.api.models import OAuthAccessToken
from pretix.api.serializers.order import (
    InvoiceSerializer, OrderCreateSerializer, OrderPaymentSerializer,
    OrderPositionSerializer, OrderRefundCreateSerializer,
    OrderRefundSerializer, OrderSerializer,
)
from pretix.base.models import (
    Invoice, Order, OrderPayment, OrderPosition, OrderRefund, Quota,
    TeamAPIToken,
)
from pretix.base.payment import PaymentException
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
    regenerate_invoice,
)
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import (
    OrderError, cancel_order, extend_order, mark_order_expired,
    mark_order_refunded,
)
from pretix.base.services.tickets import (
    get_cachedticket_for_order, get_cachedticket_for_position,
)
from pretix.base.signals import order_placed, register_ticket_outputs


class OrderFilter(FilterSet):
    email = django_filters.CharFilter(field_name='email', lookup_expr='iexact')
    code = django_filters.CharFilter(field_name='code', lookup_expr='iexact')
    status = django_filters.CharFilter(field_name='status', lookup_expr='iexact')
    modified_since = django_filters.IsoDateTimeFilter(field_name='last_modified', lookup_expr='gte')

    class Meta:
        model = Order
        fields = ['code', 'status', 'email', 'locale']


class OrderViewSet(CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('datetime',)
    ordering_fields = ('datetime', 'code', 'status')
    filterset_class = OrderFilter
    lookup_field = 'code'
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def get_queryset(self):
        return self.request.event.orders.prefetch_related(
            'positions', 'positions__checkins', 'positions__item', 'positions__answers', 'positions__answers__options',
            'positions__answers__question', 'fees', 'payments', 'refunds', 'refunds__payment'
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

    def list(self, request, **kwargs):
        date = serializers.DateTimeField().to_representation(now())
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            resp = self.get_paginated_response(serializer.data)
            resp['X-Page-Generated'] = date
            return resp

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, headers={'X-Page-Generated': date})

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

            ps = order.pending_sum
            try:
                p = order.payments.get(
                    state__in=(OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED),
                    provider='manual',
                    amount=ps
                )
            except OrderPayment.DoesNotExist:
                order.payments.filter(state__in=(OrderPayment.PAYMENT_STATE_PENDING,
                                                 OrderPayment.PAYMENT_STATE_CREATED)) \
                    .update(state=OrderPayment.PAYMENT_STATE_CANCELED)
                p = order.payments.create(
                    state=OrderPayment.PAYMENT_STATE_CREATED,
                    provider='manual',
                    amount=ps,
                    fee=None
                )

            try:
                p.confirm(auth=self.request.auth,
                          user=self.request.user if request.user.is_authenticated else None,
                          count_waitinglist=False)
            except Quota.QuotaExceededException as e:
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PaymentException as e:
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
            api_token=request.auth if isinstance(request.auth, TeamAPIToken) else None,
            oauth_application=request.auth.application if isinstance(request.auth, OAuthAccessToken) else None,
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
        order.save()
        order.log_action(
            'pretix.event.order.unpaid',
            user=request.user if request.user.is_authenticated else None,
            auth=request.auth,
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
            auth=request.auth,
        )
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def mark_refunded(self, request, **kwargs):
        order = self.get_object()

        if order.status != Order.STATUS_PAID:
            return Response(
                {'detail': 'The order is not paid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        mark_order_refunded(
            order,
            user=request.user if request.user.is_authenticated else None,
            api_token=(request.auth if isinstance(request.auth, TeamAPIToken) else None),
        )
        return self.retrieve(request, [], **kwargs)

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
                auth=request.auth,
            )
            return self.retrieve(request, [], **kwargs)
        except OrderError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            order = serializer.instance
            serializer = OrderSerializer(order, context=serializer.context)

            order.log_action(
                'pretix.event.order.placed',
                user=request.user if request.user.is_authenticated else None,
                auth=request.auth,
            )
        order_placed.send(self.request.event, order=order)

        gen_invoice = invoice_qualified(order) and (
            (order.event.settings.get('invoice_generate') == 'True') or
            (order.event.settings.get('invoice_generate') == 'paid' and order.status == Order.STATUS_PAID)
        ) and not order.invoices.last()
        if gen_invoice:
            generate_invoice(order, trigger_pdf=True)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()


class OrderPositionFilter(FilterSet):
    order = django_filters.CharFilter(field_name='order', lookup_expr='code__iexact')
    has_checkin = django_filters.rest_framework.BooleanFilter(method='has_checkin_qs')
    attendee_name = django_filters.CharFilter(method='attendee_name_qs')
    search = django_filters.CharFilter(method='search_qs')

    def search_qs(self, queryset, name, value):
        return queryset.filter(
            Q(secret__istartswith=value)
            | Q(attendee_name__icontains=value)
            | Q(addon_to__attendee_name__icontains=value)
            | Q(order__code__istartswith=value)
            | Q(order__invoice_address__name__icontains=value)
        )

    def has_checkin_qs(self, queryset, name, value):
        return queryset.filter(checkins__isnull=not value)

    def attendee_name_qs(self, queryset, name, value):
        return queryset.filter(Q(attendee_name__iexact=value) | Q(addon_to__attendee_name__iexact=value))

    class Meta:
        model = OrderPosition
        fields = {
            'item': ['exact', 'in'],
            'variation': ['exact', 'in'],
            'secret': ['exact'],
            'order__status': ['exact', 'in'],
            'addon_to': ['exact', 'in'],
            'subevent': ['exact', 'in']
        }


class OrderPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('order__datetime', 'positionid')
    ordering_fields = ('order__code', 'order__datetime', 'positionid', 'attendee_name', 'order__status',)
    filterset_class = OrderPositionFilter
    permission = 'can_view_orders'

    def get_queryset(self):
        return OrderPosition.objects.filter(order__event=self.request.event).prefetch_related(
            'checkins', 'answers', 'answers__options', 'answers__question'
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


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPaymentSerializer
    queryset = OrderPayment.objects.none()
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'
    lookup_field = 'local_id'

    def get_queryset(self):
        order = get_object_or_404(Order, code=self.kwargs['order'], event=self.request.event)
        return order.payments.all()

    @detail_route(methods=['POST'])
    def confirm(self, request, **kwargs):
        payment = self.get_object()
        force = request.data.get('force', False)

        if payment.state not in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            return Response({'detail': 'Invalid state of payment'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment.confirm(user=self.request.user if self.request.user.is_authenticated else None,
                            auth=self.request.auth,
                            count_waitinglist=False,
                            force=force)
        except Quota.QuotaExceededException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PaymentException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except SendMailException:
            pass
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def refund(self, request, **kwargs):
        payment = self.get_object()
        amount = serializers.DecimalField(max_digits=10, decimal_places=2).to_internal_value(
            request.data.get('amount', str(payment.amount))
        )
        mark_refunded = request.data.get('mark_refunded', False)

        if payment.state != OrderPayment.PAYMENT_STATE_CONFIRMED:
            return Response({'detail': 'Invalid state of payment.'}, status=status.HTTP_400_BAD_REQUEST)

        full_refund_possible = payment.payment_provider.payment_refund_supported(payment)
        partial_refund_possible = payment.payment_provider.payment_partial_refund_supported(payment)
        available_amount = payment.amount - payment.refunded_amount

        if amount <= 0:
            return Response({'amount': ['Invalid refund amount.']}, status=status.HTTP_400_BAD_REQUEST)
        if amount > available_amount:
            return Response(
                {'amount': ['Invalid refund amount, only {} are available to refund.'.format(available_amount)]},
                status=status.HTTP_400_BAD_REQUEST)
        if amount != payment.amount and not partial_refund_possible:
            return Response({'amount': ['Partial refund not available for this payment method.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if amount == payment.amount and not full_refund_possible:
            return Response({'amount': ['Full refund not available for this payment method.']},
                            status=status.HTTP_400_BAD_REQUEST)
        r = payment.order.refunds.create(
            payment=payment,
            source=OrderRefund.REFUND_SOURCE_ADMIN,
            state=OrderRefund.REFUND_STATE_CREATED,
            amount=amount,
            provider=payment.provider
        )

        try:
            r.payment_provider.execute_refund(r)
        except PaymentException as e:
            r.state = OrderRefund.REFUND_STATE_FAILED
            r.save()
            return Response({'detail': 'External error: {}'.format(str(e))},
                            status=status.HTTP_400_BAD_REQUEST)
        else:
            payment.order.log_action('pretix.event.order.refund.created', {
                'local_id': r.local_id,
                'provider': r.provider,
            }, user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
            if payment.order.pending_sum > 0:
                if mark_refunded:
                    mark_order_refunded(payment.order,
                                        user=self.request.user if self.request.user.is_authenticated else None,
                                        auth=self.request.auth)
                else:
                    payment.order.status = Order.STATUS_PENDING
                    payment.order.set_expires(
                        now(),
                        payment.order.event.subevents.filter(
                            id__in=payment.order.positions.values_list('subevent_id', flat=True))
                    )
                    payment.order.save()
            return Response(OrderRefundSerializer(r).data, status=status.HTTP_200_OK)

    @detail_route(methods=['POST'])
    def cancel(self, request, **kwargs):
        payment = self.get_object()

        if payment.state not in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            return Response({'detail': 'Invalid state of payment'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            payment.state = OrderPayment.PAYMENT_STATE_CANCELED
            payment.save()
            payment.order.log_action('pretix.event.order.payment.canceled', {
                'local_id': payment.local_id,
                'provider': payment.provider,
            }, user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        return self.retrieve(request, [], **kwargs)


class RefundViewSet(CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderRefundSerializer
    queryset = OrderRefund.objects.none()
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'
    lookup_field = 'local_id'

    def get_queryset(self):
        order = get_object_or_404(Order, code=self.kwargs['order'], event=self.request.event)
        return order.refunds.all()

    @detail_route(methods=['POST'])
    def cancel(self, request, **kwargs):
        refund = self.get_object()

        if refund.state not in (OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT,
                                OrderRefund.REFUND_STATE_EXTERNAL):
            return Response({'detail': 'Invalid state of refund'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            refund.state = OrderRefund.REFUND_STATE_CANCELED
            refund.save()
            refund.order.log_action('pretix.event.order.refund.canceled', {
                'local_id': refund.local_id,
                'provider': refund.provider,
            }, user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def process(self, request, **kwargs):
        refund = self.get_object()

        if refund.state != OrderRefund.REFUND_STATE_EXTERNAL:
            return Response({'detail': 'Invalid state of refund'}, status=status.HTTP_400_BAD_REQUEST)

        refund.done(user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        if request.data.get('mark_refunded', False):
            mark_order_refunded(refund.order, user=self.request.user if self.request.user.is_authenticated else None,
                                auth=self.request.auth)
        else:
            refund.order.status = Order.STATUS_PENDING
            refund.order.set_expires(
                now(),
                refund.order.event.subevents.filter(
                    id__in=refund.order.positions.values_list('subevent_id', flat=True))
            )
            refund.order.save()
        return self.retrieve(request, [], **kwargs)

    @detail_route(methods=['POST'])
    def done(self, request, **kwargs):
        refund = self.get_object()

        if refund.state not in (OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT):
            return Response({'detail': 'Invalid state of refund'}, status=status.HTTP_400_BAD_REQUEST)

        refund.done(user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        return self.retrieve(request, [], **kwargs)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['order'] = get_object_or_404(Order, code=self.kwargs['order'], event=self.request.event)
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = OrderRefundCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            r = serializer.instance
            serializer = OrderRefundSerializer(r, context=serializer.context)

            r.order.log_action(
                'pretix.event.order.refund.created', {
                    'local_id': r.local_id,
                    'provider': r.provider,
                },
                user=request.user if request.user.is_authenticated else None,
                auth=request.auth
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()


class InvoiceFilter(FilterSet):
    refers = django_filters.CharFilter(method='refers_qs')
    number = django_filters.CharFilter(method='nr_qs')
    order = django_filters.CharFilter(field_name='order', lookup_expr='code__iexact')

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
    filterset_class = InvoiceFilter
    permission = 'can_view_orders'
    lookup_url_kwarg = 'number'
    lookup_field = 'nr'
    write_permission = 'can_change_orders'

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

        if invoice.shredded:
            raise PermissionDenied('The invoice file is no longer stored on the server.')

        if not invoice.file:
            raise RetryException()

        resp = FileResponse(invoice.file.file, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(invoice.number)
        return resp

    @detail_route(methods=['POST'])
    def regenerate(self, request, **kwarts):
        inv = self.get_object()
        if inv.canceled:
            raise ValidationError('The invoice has already been canceled.')
        elif inv.shredded:
            raise PermissionDenied('The invoice file is no longer stored on the server.')
        else:
            inv = regenerate_invoice(inv)
            inv.order.log_action(
                'pretix.event.order.invoice.regenerated',
                data={
                    'invoice': inv.pk
                },
                user=self.request.user,
                auth=self.request.auth,
            )
            return Response(status=204)

    @detail_route(methods=['POST'])
    def reissue(self, request, **kwarts):
        inv = self.get_object()
        if inv.canceled:
            raise ValidationError('The invoice has already been canceled.')
        elif inv.shredded:
            raise PermissionDenied('The invoice file is no longer stored on the server.')
        else:
            c = generate_cancellation(inv)
            if inv.order.status not in (Order.STATUS_CANCELED, Order.STATUS_REFUNDED):
                inv = generate_invoice(inv.order)
            else:
                inv = c
            inv.order.log_action(
                'pretix.event.order.invoice.reissued',
                data={
                    'invoice': inv.pk
                },
                user=self.request.user,
                auth=self.request.auth,
            )
            return Response(status=204)
