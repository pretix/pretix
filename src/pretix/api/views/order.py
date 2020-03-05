import datetime
from decimal import Decimal

import django_filters
import pytz
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.db.models.functions import Coalesce, Concat
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.timezone import make_aware, now
from django.utils.translation import ugettext as _
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    APIException, NotFound, PermissionDenied, ValidationError,
)
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

from pretix.api.models import OAuthAccessToken
from pretix.api.serializers.order import (
    InvoiceSerializer, OrderCreateSerializer, OrderPaymentCreateSerializer,
    OrderPaymentSerializer, OrderPositionSerializer,
    OrderRefundCreateSerializer, OrderRefundSerializer, OrderSerializer,
    PriceCalcSerializer,
)
from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Device, Event, Invoice, InvoiceAddress,
    Order, OrderFee, OrderPayment, OrderPosition, OrderRefund, Quota,
    TeamAPIToken, generate_position_secret, generate_secret,
)
from pretix.base.payment import PaymentException
from pretix.base.services import tickets
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
    regenerate_invoice,
)
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _order_placed_email,
    _order_placed_email_attendee, approve_order, cancel_order, deny_order,
    extend_order, mark_order_expired, mark_order_refunded,
)
from pretix.base.services.pricing import get_price
from pretix.base.services.tickets import generate
from pretix.base.signals import (
    order_modified, order_paid, order_placed, register_ticket_outputs,
)
from pretix.base.templatetags.money import money_filter

with scopes_disabled():
    class OrderFilter(FilterSet):
        email = django_filters.CharFilter(field_name='email', lookup_expr='iexact')
        code = django_filters.CharFilter(field_name='code', lookup_expr='iexact')
        status = django_filters.CharFilter(field_name='status', lookup_expr='iexact')
        modified_since = django_filters.IsoDateTimeFilter(field_name='last_modified', lookup_expr='gte')
        created_since = django_filters.IsoDateTimeFilter(field_name='datetime', lookup_expr='gte')

        class Meta:
            model = Order
            fields = ['code', 'status', 'email', 'locale', 'testmode', 'require_approval']


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('datetime',)
    ordering_fields = ('datetime', 'code', 'status', 'last_modified')
    filterset_class = OrderFilter
    lookup_field = 'code'
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def get_queryset(self):
        if self.request.query_params.get('include_canceled_fees', 'false') == 'true':
            fqs = OrderFee.all
        else:
            fqs = OrderFee.objects
        qs = self.request.event.orders.prefetch_related(
            Prefetch('fees', queryset=fqs.all()),
            'payments', 'refunds', 'refunds__payment'
        ).select_related(
            'invoice_address'
        )

        if self.request.query_params.get('include_canceled_positions', 'false') == 'true':
            opq = OrderPosition.all
        else:
            opq = OrderPosition.objects
        if self.request.query_params.get('pdf_data', 'false') == 'true':
            qs = qs.prefetch_related(
                Prefetch(
                    'positions',
                    opq.all().prefetch_related(
                        'checkins', 'item', 'variation', 'answers', 'answers__options', 'answers__question',
                        'item__category', 'addon_to', 'seat',
                        Prefetch('addons', opq.select_related('item', 'variation', 'seat'))
                    )
                )
            )
        else:
            qs = qs.prefetch_related(
                Prefetch(
                    'positions',
                    opq.all().prefetch_related(
                        'checkins', 'item', 'variation', 'answers', 'answers__options', 'answers__question', 'seat',
                    )
                )
            )

        return qs

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

    @action(detail=True, url_name='download', url_path='download/(?P<output>[^/]+)')
    def download(self, request, output, **kwargs):
        provider = self._get_output_provider(output)
        order = self.get_object()

        if order.status != Order.STATUS_PAID:
            raise PermissionDenied("Downloads are not available for unpaid orders.")

        ct = CachedCombinedTicket.objects.filter(
            order=order, provider=provider.identifier, file__isnull=False
        ).last()
        if not ct or not ct.file:
            generate.apply_async(args=('order', order.pk, provider.identifier))
            raise RetryException()
        else:
            if ct.type == 'text/uri-list':
                resp = HttpResponse(ct.file.file.read(), content_type='text/uri-list')
                return resp
            else:
                resp = FileResponse(ct.file.file, content_type=ct.type)
                resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}{}"'.format(
                    self.request.event.slug.upper(), order.code,
                    provider.identifier, ct.extension
                )
                return resp

    @action(detail=True, methods=['POST'])
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
                for p in order.payments.filter(state__in=(OrderPayment.PAYMENT_STATE_PENDING,
                                                          OrderPayment.PAYMENT_STATE_CREATED)):
                    try:
                        with transaction.atomic():
                            p.payment_provider.cancel_payment(p)
                            order.log_action('pretix.event.order.payment.canceled', {
                                'local_id': p.local_id,
                                'provider': p.provider,
                            }, user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
                    except PaymentException as e:
                        order.log_action(
                            'pretix.event.order.payment.canceled.failed',
                            {
                                'local_id': p.local_id,
                                'provider': p.provider,
                                'error': str(e)
                            },
                            user=self.request.user if self.request.user.is_authenticated else None,
                            auth=self.request.auth
                        )
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

    @action(detail=True, methods=['POST'])
    def mark_canceled(self, request, **kwargs):
        send_mail = request.data.get('send_email', True)
        cancellation_fee = request.data.get('cancellation_fee', None)
        if cancellation_fee:
            try:
                cancellation_fee = float(Decimal(cancellation_fee))
            except:
                cancellation_fee = None

        order = self.get_object()
        if not order.cancel_allowed():
            return Response(
                {'detail': 'The order is not allowed to be canceled.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            cancel_order(
                order,
                user=request.user if request.user.is_authenticated else None,
                api_token=request.auth if isinstance(request.auth, TeamAPIToken) else None,
                device=request.auth if isinstance(request.auth, Device) else None,
                oauth_application=request.auth.application if isinstance(request.auth, OAuthAccessToken) else None,
                send_mail=send_mail,
                cancellation_fee=cancellation_fee
            )
        except OrderError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
    def approve(self, request, **kwargs):
        send_mail = request.data.get('send_email', True)

        order = self.get_object()
        try:
            approve_order(
                order,
                user=request.user if request.user.is_authenticated else None,
                auth=request.auth if isinstance(request.auth, (Device, TeamAPIToken, OAuthAccessToken)) else None,
                send_mail=send_mail,
            )
        except Quota.QuotaExceededException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except OrderError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
    def deny(self, request, **kwargs):
        send_mail = request.data.get('send_email', True)
        comment = request.data.get('comment', '')

        order = self.get_object()
        try:
            deny_order(
                order,
                user=request.user if request.user.is_authenticated else None,
                auth=request.auth if isinstance(request.auth, (Device, TeamAPIToken, OAuthAccessToken)) else None,
                send_mail=send_mail,
                comment=comment,
            )
        except OrderError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
    def mark_pending(self, request, **kwargs):
        order = self.get_object()

        if order.status != Order.STATUS_PAID:
            return Response(
                {'detail': 'The order is not paid.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = Order.STATUS_PENDING
        order.save(update_fields=['status'])
        order.log_action(
            'pretix.event.order.unpaid',
            user=request.user if request.user.is_authenticated else None,
            auth=request.auth,
        )
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
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

    @action(detail=True, methods=['POST'])
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
            auth=(request.auth if isinstance(request.auth, (TeamAPIToken, OAuthAccessToken, Device)) else None),
        )
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
    def create_invoice(self, request, **kwargs):
        order = self.get_object()
        has_inv = order.invoices.exists() and not (
            order.status in (Order.STATUS_PAID, Order.STATUS_PENDING)
            and order.invoices.filter(is_cancellation=True).count() >= order.invoices.filter(is_cancellation=False).count()
        )
        if self.request.event.settings.get('invoice_generate') not in ('admin', 'user', 'paid', 'True') or not invoice_qualified(order):
            return Response(
                {'detail': _('You cannot generate an invoice for this order.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif has_inv:
            return Response(
                {'detail': _('An invoice for this order already exists.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        inv = generate_invoice(order)
        order.log_action(
            'pretix.event.order.invoice.generated',
            user=self.request.user,
            auth=self.request.auth,
            data={
                'invoice': inv.pk
            }
        )
        return Response(
            InvoiceSerializer(inv).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['POST'])
    def resend_link(self, request, **kwargs):
        order = self.get_object()
        if not order.email:
            return Response({'detail': 'There is no email address associated with this order.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order.resend_link(user=self.request.user, auth=self.request.auth)
        except SendMailException:
            return Response({'detail': _('There was an error sending the mail. Please try again later.')}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )

    @action(detail=True, methods=['POST'])
    @transaction.atomic
    def regenerate_secrets(self, request, **kwargs):
        order = self.get_object()
        order.secret = generate_secret()
        for op in order.all_positions.all():
            op.secret = generate_position_secret()
            op.save()
        order.save(update_fields=['secret'])
        CachedTicket.objects.filter(order_position__order=order).delete()
        CachedCombinedTicket.objects.filter(order=order).delete()
        tickets.invalidate_cache.apply_async(kwargs={'event': self.request.event.pk,
                                                     'order': order.pk})
        order.log_action(
            'pretix.event.order.secret.changed',
            user=self.request.user,
            auth=self.request.auth,
        )
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
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
            send_mail = serializer._send_mail
            order = serializer.instance
            serializer = OrderSerializer(order, context=serializer.context)
            if not order.pk:
                # Simulation
                return Response(serializer.data, status=status.HTTP_201_CREATED)

            order.log_action(
                'pretix.event.order.placed',
                user=request.user if request.user.is_authenticated else None,
                auth=request.auth,
            )

        with language(order.locale):
            order_placed.send(self.request.event, order=order)
            if order.status == Order.STATUS_PAID:
                order_paid.send(self.request.event, order=order)

            gen_invoice = invoice_qualified(order) and (
                (order.event.settings.get('invoice_generate') == 'True') or
                (order.event.settings.get('invoice_generate') == 'paid' and order.status == Order.STATUS_PAID)
            ) and not order.invoices.last()
            invoice = None
            if gen_invoice:
                invoice = generate_invoice(order, trigger_pdf=True)

            if send_mail:
                payment = order.payments.last()
                free_flow = (
                    payment and order.total == Decimal('0.00') and order.status == Order.STATUS_PAID and
                    not order.require_approval and payment.provider == "free"
                )
                if free_flow:
                    email_template = request.event.settings.mail_text_order_free
                    log_entry = 'pretix.event.order.email.order_free'
                    email_attendees = request.event.settings.mail_send_order_free_attendee
                    email_attendees_template = request.event.settings.mail_text_order_free_attendee
                else:
                    email_template = request.event.settings.mail_text_order_placed
                    log_entry = 'pretix.event.order.email.order_placed'
                    email_attendees = request.event.settings.mail_send_order_placed_attendee
                    email_attendees_template = request.event.settings.mail_text_order_placed_attendee

                _order_placed_email(
                    request.event, order, payment.payment_provider if payment else None, email_template,
                    log_entry, invoice, payment
                )
                if email_attendees:
                    for p in order.positions.all():
                        if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                            _order_placed_email_attendee(request.event, order, p, email_attendees_template, log_entry)

                if not free_flow and order.status == Order.STATUS_PAID and payment:
                    payment._send_paid_mail(invoice, None, '')
                    if self.request.event.settings.mail_send_order_paid_attendee:
                        for p in order.positions.all():
                            if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                                payment._send_paid_mail_attendee(p, None)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.get('partial', False)
        if not partial:
            return Response(
                {"detail": "Method \"PUT\" not allowed."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with transaction.atomic():
            if 'comment' in self.request.data and serializer.instance.comment != self.request.data.get('comment'):
                serializer.instance.log_action(
                    'pretix.event.order.comment',
                    user=self.request.user,
                    auth=self.request.auth,
                    data={
                        'new_comment': self.request.data.get('comment')
                    }
                )

            if 'checkin_attention' in self.request.data and serializer.instance.checkin_attention != self.request.data.get('checkin_attention'):
                serializer.instance.log_action(
                    'pretix.event.order.checkin_attention',
                    user=self.request.user,
                    auth=self.request.auth,
                    data={
                        'new_value': self.request.data.get('checkin_attention')
                    }
                )

            if 'email' in self.request.data and serializer.instance.email != self.request.data.get('email'):
                serializer.instance.email_known_to_work = False
                serializer.instance.log_action(
                    'pretix.event.order.contact.changed',
                    user=self.request.user,
                    auth=self.request.auth,
                    data={
                        'old_email': serializer.instance.email,
                        'new_email': self.request.data.get('email'),
                    }
                )

            if 'locale' in self.request.data and serializer.instance.locale != self.request.data.get('locale'):
                serializer.instance.log_action(
                    'pretix.event.order.locale.changed',
                    user=self.request.user,
                    auth=self.request.auth,
                    data={
                        'old_locale': serializer.instance.locale,
                        'new_locale': self.request.data.get('locale'),
                    }
                )

            if 'invoice_address' in self.request.data:
                serializer.instance.log_action(
                    'pretix.event.order.modified',
                    user=self.request.user,
                    auth=self.request.auth,
                    data={
                        'invoice_data': self.request.data.get('invoice_address'),
                    }
                )

            serializer.save()
            tickets.invalidate_cache.apply_async(kwargs={'event': serializer.instance.event.pk, 'order': serializer.instance.pk})

        if 'invoice_address' in self.request.data:
            order_modified.send(sender=serializer.instance.event, order=serializer.instance)

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.testmode:
            raise PermissionDenied('Only test mode orders can be deleted.')

        with transaction.atomic():
            self.get_object().gracefully_delete(user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)


with scopes_disabled():
    class OrderPositionFilter(FilterSet):
        order = django_filters.CharFilter(field_name='order', lookup_expr='code__iexact')
        has_checkin = django_filters.rest_framework.BooleanFilter(method='has_checkin_qs')
        attendee_name = django_filters.CharFilter(method='attendee_name_qs')
        search = django_filters.CharFilter(method='search_qs')

        def search_qs(self, queryset, name, value):
            return queryset.filter(
                Q(secret__istartswith=value)
                | Q(attendee_name_cached__icontains=value)
                | Q(addon_to__attendee_name_cached__icontains=value)
                | Q(attendee_email__icontains=value)
                | Q(addon_to__attendee_email__icontains=value)
                | Q(order__code__istartswith=value)
                | Q(order__invoice_address__name_cached__icontains=value)
                | Q(order__email__icontains=value)
            )

        def has_checkin_qs(self, queryset, name, value):
            return queryset.filter(checkins__isnull=not value)

        def attendee_name_qs(self, queryset, name, value):
            return queryset.filter(Q(attendee_name_cached__iexact=value) | Q(addon_to__attendee_name_cached__iexact=value))

        class Meta:
            model = OrderPosition
            fields = {
                'item': ['exact', 'in'],
                'variation': ['exact', 'in'],
                'secret': ['exact'],
                'order__status': ['exact', 'in'],
                'addon_to': ['exact', 'in'],
                'subevent': ['exact', 'in'],
                'pseudonymization_id': ['exact'],
                'voucher__code': ['exact'],
                'voucher': ['exact'],
            }


class OrderPositionViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPositionSerializer
    queryset = OrderPosition.all.none()
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering = ('order__datetime', 'positionid')
    ordering_fields = ('order__code', 'order__datetime', 'positionid', 'attendee_name', 'order__status',)
    filterset_class = OrderPositionFilter
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'
    ordering_custom = {
        'attendee_name': {
            '_order': F('display_name').asc(nulls_first=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        '-attendee_name': {
            '_order': F('display_name').asc(nulls_last=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
    }

    def get_queryset(self):
        if self.request.query_params.get('include_canceled_positions', 'false') == 'true':
            qs = OrderPosition.all
        else:
            qs = OrderPosition.objects

        qs = qs.filter(order__event=self.request.event)
        if self.request.query_params.get('pdf_data', 'false') == 'true':
            qs = qs.prefetch_related(
                'checkins', 'answers', 'answers__options', 'answers__question',
                Prefetch('addons', qs.select_related('item', 'variation')),
                Prefetch('order', Order.objects.select_related('invoice_address').prefetch_related(
                    Prefetch(
                        'event',
                        Event.objects.select_related('organizer')
                    ),
                    Prefetch(
                        'positions',
                        qs.prefetch_related(
                            'checkins', 'item', 'variation', 'answers', 'answers__options', 'answers__question',
                        )
                    )
                ))
            ).select_related(
                'item', 'variation', 'item__category', 'addon_to', 'seat'
            )
        else:
            qs = qs.prefetch_related(
                'checkins', 'answers', 'answers__options', 'answers__question',
            ).select_related(
                'item', 'order', 'order__event', 'order__event__organizer', 'seat'
            )
        return qs

    def _get_output_provider(self, identifier):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            prov = response(self.request.event)
            if prov.identifier == identifier:
                return prov
        raise NotFound('Unknown output provider.')

    @action(detail=True, methods=['POST'], url_name='price_calc')
    def price_calc(self, request, *args, **kwargs):
        """
        This calculates the price assuming a change of product or subevent. This endpoint
        is deliberately not documented and considered a private API, only to be used by
        pretix' web interface.

        Sample input:

        {
            "item": 2,
            "variation": null,
            "subevent": 3
        }

        Sample output:

        {
            "gross": "2.34",
            "gross_formatted": "2,34",
            "net": "2.34",
            "tax": "0.00",
            "rate": "0.00",
            "name": "VAT"
        }
        """
        serializer = PriceCalcSerializer(data=request.data, event=request.event)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        pos = self.get_object()

        try:
            ia = pos.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = InvoiceAddress()

        kwargs = {
            'item': pos.item,
            'variation': pos.variation,
            'voucher': pos.voucher,
            'subevent': pos.subevent,
            'addon_to': pos.addon_to,
            'invoice_address': ia,
        }

        if data.get('item'):
            item = data.get('item')
            kwargs['item'] = item

            if item.has_variations:
                variation = data.get('variation') or pos.variation
                if not variation:
                    raise ValidationError('No variation given')
                if variation.item != item:
                    raise ValidationError('Variation does not belong to item')
                kwargs['variation'] = variation
            else:
                variation = None
                kwargs['variation'] = None

            if pos.voucher and not pos.voucher.applies_to(item, variation):
                kwargs['voucher'] = None

        if data.get('subevent'):
            kwargs['subevent'] = data.get('subevent')

        price = get_price(**kwargs)
        with language(data.get('locale') or self.request.event.settings.locale):
            return Response({
                'gross': price.gross,
                'gross_formatted': money_filter(price.gross, self.request.event.currency, hide_currency=True),
                'net': price.net,
                'rate': price.rate,
                'name': str(price.name),
                'tax': price.tax,
            })

    @action(detail=True, url_name='download', url_path='download/(?P<output>[^/]+)')
    def download(self, request, output, **kwargs):
        provider = self._get_output_provider(output)
        pos = self.get_object()

        if pos.order.status != Order.STATUS_PAID:
            raise PermissionDenied("Downloads are not available for unpaid orders.")
        if not pos.generate_ticket:
            raise PermissionDenied("Downloads are not enabled for this product.")

        ct = CachedTicket.objects.filter(
            order_position=pos, provider=provider.identifier, file__isnull=False
        ).last()
        if not ct or not ct.file:
            generate.apply_async(args=('orderposition', pos.pk, provider.identifier))
            raise RetryException()
        else:
            if ct.type == 'text/uri-list':
                resp = HttpResponse(ct.file.file.read(), content_type='text/uri-list')
                return resp
            else:
                resp = FileResponse(ct.file.file, content_type=ct.type)
                resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}-{}{}"'.format(
                    self.request.event.slug.upper(), pos.order.code, pos.positionid,
                    provider.identifier, ct.extension
                )
                return resp

    def perform_destroy(self, instance):
        try:
            ocm = OrderChangeManager(
                instance.order,
                user=self.request.user if self.request.user.is_authenticated else None,
                auth=self.request.auth,
                notify=False
            )
            ocm.cancel(instance)
            ocm.commit()
        except OrderError as e:
            raise ValidationError(str(e))
        except Quota.QuotaExceededException as e:
            raise ValidationError(str(e))


class PaymentViewSet(CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderPaymentSerializer
    queryset = OrderPayment.objects.none()
    permission = 'can_view_orders'
    write_permission = 'can_change_orders'
    lookup_field = 'local_id'

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['order'] = get_object_or_404(Order, code=self.kwargs['order'], event=self.request.event)
        return ctx

    def get_queryset(self):
        order = get_object_or_404(Order, code=self.kwargs['order'], event=self.request.event)
        return order.payments.all()

    def create(self, request, *args, **kwargs):
        serializer = OrderPaymentCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            mark_confirmed = False
            if serializer.validated_data['state'] == OrderPayment.PAYMENT_STATE_CONFIRMED:
                serializer.validated_data['state'] = OrderPayment.PAYMENT_STATE_PENDING
                mark_confirmed = True
            self.perform_create(serializer)
            r = serializer.instance
            if mark_confirmed:
                try:
                    r.confirm(
                        user=self.request.user if self.request.user.is_authenticated else None,
                        auth=self.request.auth,
                        count_waitinglist=False,
                        force=request.data.get('force', False)
                    )
                except Quota.QuotaExceededException:
                    pass
                except SendMailException:
                    pass

            serializer = OrderPaymentSerializer(r, context=serializer.context)

            r.order.log_action(
                'pretix.event.order.payment.started', {
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

    @action(detail=True, methods=['POST'])
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

    @action(detail=True, methods=['POST'])
    def refund(self, request, **kwargs):
        payment = self.get_object()
        amount = serializers.DecimalField(max_digits=10, decimal_places=2).to_internal_value(
            request.data.get('amount', str(payment.amount))
        )
        if 'mark_refunded' in request.data:
            mark_refunded = request.data.get('mark_refunded', False)
        else:
            mark_refunded = request.data.get('mark_canceled', False)

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
                    payment.order.save(update_fields=['status', 'expires'])
            return Response(OrderRefundSerializer(r).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'])
    def cancel(self, request, **kwargs):
        payment = self.get_object()

        if payment.state not in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
            return Response({'detail': 'Invalid state of payment'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                payment.payment_provider.cancel_payment(payment)
                payment.order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': payment.local_id,
                    'provider': payment.provider,
                }, user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        except PaymentException as e:
            return Response({'detail': 'External error: {}'.format(str(e))},
                            status=status.HTTP_400_BAD_REQUEST)
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

    @action(detail=True, methods=['POST'])
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

    @action(detail=True, methods=['POST'])
    def process(self, request, **kwargs):
        refund = self.get_object()

        if refund.state != OrderRefund.REFUND_STATE_EXTERNAL:
            return Response({'detail': 'Invalid state of refund'}, status=status.HTTP_400_BAD_REQUEST)

        refund.done(user=self.request.user if self.request.user.is_authenticated else None, auth=self.request.auth)
        if 'mark_refunded' in request.data:
            mark_refunded = request.data.get('mark_refunded', False)
        else:
            mark_refunded = request.data.get('mark_canceled', False)
        if mark_refunded:
            mark_order_refunded(refund.order, user=self.request.user if self.request.user.is_authenticated else None,
                                auth=self.request.auth)
        elif not (refund.order.status == Order.STATUS_PAID and refund.order.pending_sum <= 0):
            refund.order.status = Order.STATUS_PENDING
            refund.order.set_expires(
                now(),
                refund.order.event.subevents.filter(
                    id__in=refund.order.positions.values_list('subevent_id', flat=True))
            )
            refund.order.save(update_fields=['status', 'expires'])
        return self.retrieve(request, [], **kwargs)

    @action(detail=True, methods=['POST'])
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
        if 'mark_refunded' in request.data:
            mark_refunded = request.data.pop('mark_refunded', False)
        else:
            mark_refunded = request.data.pop('mark_canceled', False)
        mark_pending = request.data.pop('mark_pending', False)
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
            if mark_refunded:
                try:
                    mark_order_refunded(
                        r.order,
                        user=request.user if request.user.is_authenticated else None,
                        auth=(request.auth if request.auth else None),
                    )
                except OrderError as e:
                    raise ValidationError(str(e))
            elif mark_pending:
                if r.order.status == Order.STATUS_PAID and r.order.pending_sum > 0:
                    r.order.status = Order.STATUS_PENDING
                    r.order.set_expires(
                        now(),
                        r.order.event.subevents.filter(
                            id__in=r.order.positions.values_list('subevent_id', flat=True))
                    )
                    r.order.save(update_fields=['status', 'expires'])

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()


with scopes_disabled():
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

    @action(detail=True, )
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

    @action(detail=True, methods=['POST'])
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

    @action(detail=True, methods=['POST'])
    def reissue(self, request, **kwarts):
        inv = self.get_object()
        if inv.canceled:
            raise ValidationError('The invoice has already been canceled.')
        elif inv.shredded:
            raise PermissionDenied('The invoice file is no longer stored on the server.')
        else:
            c = generate_cancellation(inv)
            if inv.order.status != Order.STATUS_CANCELED:
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
