import json
import logging
import mimetypes
import os
from datetime import timedelta
from decimal import Decimal, DecimalException

import pytz
import vat_moss.id
from django.conf import settings
from django.contrib import messages
from django.core.files import File
from django.db import transaction
from django.db.models import Count
from django.http import (
    FileResponse, Http404, HttpResponseNotAllowed, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.http import is_safe_url
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    DetailView, FormView, ListView, TemplateView, View,
)
from i18nfield.strings import LazyI18nString

from pretix.base.channels import get_all_sales_channels
from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedFile, CachedTicket, Invoice, InvoiceAddress,
    Item, ItemVariation, LogEntry, Order, QuestionAnswer, Quota,
    generate_position_secret, generate_secret,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import (
    OrderFee, OrderPayment, OrderPosition, OrderRefund,
)
from pretix.base.models.tax import EU_COUNTRIES
from pretix.base.payment import PaymentException
from pretix.base.services.export import export
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_pdf_task,
    invoice_qualified, regenerate_invoice,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, render_mail
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, approve_order, cancel_order, deny_order,
    extend_order, mark_order_expired, mark_order_refunded,
)
from pretix.base.services.stats import order_overview
from pretix.base.services.tickets import generate
from pretix.base.signals import (
    register_data_exporters, register_ticket_outputs,
)
from pretix.base.templatetags.money import money_filter
from pretix.base.views.mixins import OrderQuestionsViewMixin
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.filter import EventOrderFilterForm, RefundFilterForm
from pretix.control.forms.orders import (
    CommentForm, ConfirmPaymentForm, ExporterForm, ExtendForm, MarkPaidForm,
    OrderContactForm, OrderLocaleForm, OrderMailForm, OrderPositionAddForm,
    OrderPositionChangeForm, OrderRefundForm, OtherOperationsForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import PaginationMixin
from pretix.helpers.safedownload import check_token
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


class OrderList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = Order
    context_object_name = 'orders'
    template_name = 'pretixcontrol/orders/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = Order.objects.filter(
            event=self.request.event
        ).annotate(pcnt=Count('positions', distinct=True)).select_related('invoice_address')

        qs = Order.annotate_overpayments(qs)

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return EventOrderFilterForm(data=self.request.GET, event=self.request.event)


class OrderView(EventPermissionRequiredMixin, DetailView):
    context_object_name = 'order'
    model = Order

    def get_object(self, queryset=None):
        try:
            return Order.objects.get(
                event=self.request.event,
                code=self.kwargs['code'].upper()
            )
        except Order.DoesNotExist:
            raise Http404()

    def _redirect_back(self):
        return redirect('control:event.order',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        code=self.order.code)

    @cached_property
    def order(self):
        return self.get_object()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_generate_invoice'] = invoice_qualified(self.order) and (
            self.request.event.settings.invoice_generate in ('admin', 'user', 'paid', 'True')
        ) and (
            not self.order.invoices.exists()
            or (
                self.order.status in (Order.STATUS_PAID, Order.STATUS_PENDING)
                and self.order.invoices.filter(is_cancellation=True).count() >= self.order.invoices.filter(is_cancellation=False).count()
            )
        )
        return ctx

    def get_order_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.order.code
        })


class OrderDetail(OrderView):
    template_name = 'pretixcontrol/order/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.get_items()
        ctx['event'] = self.request.event
        ctx['payments'] = self.order.payments.order_by('-created')
        ctx['refunds'] = self.order.refunds.select_related('payment').order_by('-created')
        for p in ctx['payments']:
            if p.payment_provider:
                p.html_info = (p.payment_provider.payment_control_render(self.request, p) or "").strip()
        ctx['invoices'] = list(self.order.invoices.all().select_related('event'))
        ctx['comment_form'] = CommentForm(initial={
            'comment': self.order.comment,
            'checkin_attention': self.order.checkin_attention
        })
        ctx['display_locale'] = dict(settings.LANGUAGES)[self.object.locale or self.request.event.settings.locale]

        ctx['overpaid'] = self.order.pending_sum * -1
        ctx['sales_channel'] = get_all_sales_channels().get(self.order.sales_channel)
        ctx['download_buttons'] = self.download_buttons
        return ctx

    @cached_property
    def download_buttons(self):
        buttons = []

        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            buttons.append({
                'text': provider.download_button_text or 'Ticket',
                'icon': provider.download_button_icon or 'fa-download',
                'identifier': provider.identifier,
                'multi': provider.multi_download_enabled
            })
        return buttons

    def get_items(self):
        queryset = self.object.positions.all()

        cartpos = queryset.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation', 'addon_to', 'tax_rule'
        ).prefetch_related(
            'item__questions', 'answers', 'answers__question', 'checkins', 'checkins__list'
        ).order_by('positionid')

        positions = []
        for p in cartpos:
            responses = question_form_fields.send(sender=self.request.event, position=p)
            p.additional_fields = []
            data = p.meta_info_data
            for r, response in sorted(responses, key=lambda r: str(r[0])):
                if response:
                    for key, value in response.items():
                        p.additional_fields.append({
                            'answer': data.get('question_form_data', {}).get(key),
                            'question': value.label
                        })

            p.has_questions = (
                p.additional_fields or
                (p.item.admission and self.request.event.settings.attendee_names_asked) or
                (p.item.admission and self.request.event.settings.attendee_emails_asked) or
                p.item.questions.all()
            )
            p.cache_answers()

            positions.append(p)

        positions.sort(key=lambda p: p.sort_key)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.object.total,
            'fees': self.object.fees.all(),
            'net_total': self.object.net_total,
            'tax_total': self.object.tax_total,
        }


class OrderDownload(AsyncAction, OrderView):
    task = generate
    permission = 'can_view_orders'

    def get_success_url(self, value):
        return self.get_self_url()

    def get_error_url(self):
        return self.get_order_url()

    def get_self_url(self):
        return reverse('control:event.order.download.ticket', kwargs=self.kwargs)

    @cached_property
    def output(self):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.kwargs.get('output'):
                return provider

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(pk=self.kwargs.get('position'))
        except OrderPosition.DoesNotExist:
            return None

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        ct = self.get_last_ct()
        if ct:
            return self.success(ct)
        return self.http_method_not_allowed(request)

    def post(self, request, *args, **kwargs):
        if not self.output:
            return self.error(_('You requested an invalid ticket output type.'))
        if not self.order_position:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if 'position' in kwargs and (self.order_position.addon_to and not self.request.event.settings.ticket_download_addons):
            return self.error(_('Ticket download is not enabled for add-on products.'))
        if 'position' in kwargs and (not self.order_position.item.admission and not self.request.event.settings.ticket_download_nonadm):
            return self.error(_('Ticket download is not enabled for non-admission products.'))

        ct = self.get_last_ct()
        if ct:
            return self.success(ct)
        return self.do('orderposition' if 'position' in kwargs else 'order',
                       self.order_position.pk if 'position' in kwargs else self.order.pk,
                       self.output.identifier)

    def get_success_message(self, value):
        return ""

    def success(self, value):
        if "ajax" in self.request.POST or "ajax" in self.request.GET:
            return JsonResponse({
                'ready': True,
                'success': True,
                'redirect': self.get_success_url(value),
                'message': str(self.get_success_message(value))
            })
        if isinstance(value, CachedTicket):
            resp = FileResponse(value.file.file, content_type=value.type)
            resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}-{}{}"'.format(
                self.request.event.slug.upper(), self.order.code, self.order_position.positionid,
                self.output.identifier, value.extension
            )
            return resp
        elif isinstance(value, CachedCombinedTicket):
            resp = FileResponse(value.file.file, content_type=value.type)
            resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}{}"'.format(
                self.request.event.slug.upper(), self.order.code, self.output.identifier, value.extension
            )
            return resp
        else:
            return redirect(self.get_self_url())

    def get_last_ct(self):
        if 'position' in self.kwargs:
            ct = CachedTicket.objects.filter(
                order_position=self.order_position, provider=self.output.identifier, file__isnull=False
            ).last()
        else:
            ct = CachedCombinedTicket.objects.filter(
                order=self.order, provider=self.output.identifier, file__isnull=False
            ).last()
        if not ct or not ct.file:
            return None
        return ct


class OrderComment(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        form = CommentForm(self.request.POST)
        if form.is_valid():
            if form.cleaned_data.get('comment') != self.order.comment:
                self.order.comment = form.cleaned_data.get('comment')
                self.order.log_action('pretix.event.order.comment', user=self.request.user, data={
                    'new_comment': form.cleaned_data.get('comment')
                })

            if form.cleaned_data.get('checkin_attention') != self.order.checkin_attention:
                self.order.checkin_attention = form.cleaned_data.get('checkin_attention')
                self.order.log_action('pretix.event.order.checkin_attention', user=self.request.user, data={
                    'new_value': form.cleaned_data.get('checkin_attention')
                })
            self.order.save(update_fields=['checkin_attention', 'comment'])
            messages.success(self.request, _('The comment has been updated.'))
        else:
            messages.error(self.request, _('Could not update the comment.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderApprove(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.order.require_approval:
            try:
                approve_order(self.order, user=self.request.user)
            except OrderError as e:
                messages.error(self.request, str(e))
            else:
                messages.success(self.request, _('The order has been approved.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/approve.html', {
            'order': self.order,
        })


class OrderDeny(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.order.require_approval:
            try:
                deny_order(self.order, user=self.request.user,
                           comment=self.request.POST.get('comment'),
                           send_mail=self.request.POST.get('send_email') == 'on')
            except OrderError as e:
                messages.error(self.request, str(e))
            else:
                messages.success(self.request, _('The order has been denied and is therefore now canceled.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/deny.html', {
            'order': self.order,
        })


class OrderPaymentCancel(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments, pk=self.kwargs['payment'])

    def post(self, *args, **kwargs):
        if self.payment.state in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
            with transaction.atomic():
                self.payment.state = OrderPayment.PAYMENT_STATE_CANCELED
                self.payment.save()
                self.order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': self.payment.local_id,
                    'provider': self.payment.provider,
                }, user=self.request.user)
            messages.success(self.request, _('This payment has been canceled.'))
        else:
            messages.error(self.request, _('This payment can not be canceled at the moment.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/pay_cancel.html', {
            'order': self.order,
        })


class OrderRefundCancel(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def refund(self):
        return get_object_or_404(self.order.refunds, pk=self.kwargs['refund'])

    def post(self, *args, **kwargs):
        if self.refund.state in (OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT,
                                 OrderRefund.REFUND_STATE_EXTERNAL):
            with transaction.atomic():
                self.refund.state = OrderRefund.REFUND_STATE_CANCELED
                self.refund.save()
                self.order.log_action('pretix.event.order.refund.canceled', {
                    'local_id': self.refund.local_id,
                    'provider': self.refund.provider,
                }, user=self.request.user)
            messages.success(self.request, _('The refund has been canceled.'))
        else:
            messages.error(self.request, _('This refund can not be canceled at the moment.'))
        if "next" in self.request.GET and is_safe_url(self.request.GET.get("next"), allowed_hosts=None):
            return redirect(self.request.GET.get("next"))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/refund_cancel.html', {
            'order': self.order,
        })


class OrderRefundProcess(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def refund(self):
        return get_object_or_404(self.order.refunds, pk=self.kwargs['refund'])

    def post(self, *args, **kwargs):
        if self.refund.state == OrderRefund.REFUND_STATE_EXTERNAL:
            self.refund.done(user=self.request.user)

            if self.request.POST.get("action") == "r":
                mark_order_refunded(self.order, user=self.request.user)
            else:
                self.order.status = Order.STATUS_PENDING
                self.order.set_expires(
                    now(),
                    self.order.event.subevents.filter(
                        id__in=self.order.positions.values_list('subevent_id', flat=True))
                )
                self.order.save(update_fields=['status', 'expires'])

            messages.success(self.request, _('The refund has been processed.'))
        else:
            messages.error(self.request, _('This refund can not be processed at the moment.'))
        if "next" in self.request.GET and is_safe_url(self.request.GET.get("next"), allowed_hosts=None):
            return redirect(self.request.GET.get("next"))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/refund_process.html', {
            'order': self.order,
            'refund': self.refund,
            'pending_sum': self.order.pending_sum + self.refund.amount,
            'propose_cancel': self.order.pending_sum + self.refund.amount >= self.order.total
        })


class OrderRefundDone(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def refund(self):
        return get_object_or_404(self.order.refunds, pk=self.kwargs['refund'])

    def post(self, *args, **kwargs):
        if self.refund.state in (OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT):
            self.refund.done(user=self.request.user)
            messages.success(self.request, _('The refund has been marked as done.'))
        else:
            messages.error(self.request, _('This refund can not be processed at the moment.'))
        if "next" in self.request.GET and is_safe_url(self.request.GET.get("next"), allowed_hosts=None):
            return redirect(self.request.GET.get("next"))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/refund_done.html', {
            'order': self.order,
        })


class OrderPaymentConfirm(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments, pk=self.kwargs['payment'])

    @cached_property
    def mark_paid_form(self):
        return ConfirmPaymentForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None,
        )

    def post(self, *args, **kwargs):
        if self.payment.state in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
            if not self.mark_paid_form.is_valid():
                return render(self.request, 'pretixcontrol/order/pay_complete.html', {
                    'form': self.mark_paid_form,
                    'order': self.order,
                })
            try:
                self.payment.confirm(user=self.request.user,
                                     count_waitinglist=False,
                                     force=self.mark_paid_form.cleaned_data.get('force', False))
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
            except PaymentException as e:
                messages.error(self.request, str(e))
            except SendMailException:
                messages.warning(self.request,
                                 _('The payment has been marked as complete, but we were unable to send a '
                                   'confirmation mail.'))
            else:
                messages.success(self.request, _('The payment has been marked as complete.'))
        else:
            messages.error(self.request, _('This payment can not be confirmed at the moment.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/pay_complete.html', {
            'form': self.mark_paid_form,
            'order': self.order,
        })


class OrderRefundView(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def start_form(self):
        return OrderRefundForm(
            order=self.order,
            data=self.request.POST if self.request.method == "POST" else None,
            prefix='start',
            initial={
                'partial_amount': self.order.payment_refund_sum,
                'action': (
                    'mark_pending' if self.order.status == Order.STATUS_PAID
                    else 'do_nothing'
                )
            }
        )

    def post(self, *args, **kwargs):
        if self.start_form.is_valid():
            payments = self.order.payments.filter(
                state=OrderPayment.PAYMENT_STATE_CONFIRMED
            )
            for p in payments:
                p.full_refund_possible = p.payment_provider.payment_refund_supported(p)
                p.partial_refund_possible = p.payment_provider.payment_partial_refund_supported(p)
                p.propose_refund = Decimal('0.00')
                p.available_amount = p.amount - p.refunded_amount

            unused_payments = set(p for p in payments if p.full_refund_possible or p.partial_refund_possible)

            # Algorithm to choose which payments are to be refunded to create the least hassle
            if self.start_form.cleaned_data.get('mode') == 'full':
                to_refund = full_refund = self.order.payment_refund_sum
            else:
                to_refund = full_refund = self.start_form.cleaned_data.get('partial_amount')

            while to_refund and unused_payments:
                bigger = sorted([p for p in unused_payments if p.available_amount > to_refund],
                                key=lambda p: p.available_amount)
                same = [p for p in unused_payments if p.available_amount == to_refund]
                smaller = sorted([p for p in unused_payments if p.available_amount < to_refund],
                                 key=lambda p: p.available_amount,
                                 reverse=True)
                if same:
                    for payment in same:
                        if payment.full_refund_possible or payment.partial_refund_possible:
                            payment.propose_refund = payment.available_amount
                            to_refund -= payment.available_amount
                            unused_payments.remove(payment)
                            break
                elif bigger:
                    for payment in bigger:
                        if payment.partial_refund_possible:
                            payment.propose_refund = to_refund
                            to_refund -= to_refund
                            unused_payments.remove(payment)
                            break
                elif smaller:
                    for payment in smaller:
                        if payment.full_refund_possible or payment.partial_refund_possible:
                            payment.propose_refund = payment.available_amount
                            to_refund -= payment.available_amount
                            unused_payments.remove(payment)
                            break

            if 'perform' in self.request.POST:
                refund_selected = Decimal('0.00')
                refunds = []

                is_valid = True
                manual_value = self.request.POST.get('refund-manual', '0') or '0'
                manual_value = formats.sanitize_separators(manual_value)
                try:
                    manual_value = Decimal(manual_value)
                except (DecimalException, TypeError):
                    messages.error(self.request, _('You entered an invalid number.'))
                    is_valid = False
                else:
                    refund_selected += manual_value
                    if manual_value:
                        refunds.append(OrderRefund(
                            order=self.order,
                            payment=None,
                            source=OrderRefund.REFUND_SOURCE_ADMIN,
                            state=(
                                OrderRefund.REFUND_STATE_DONE
                                if self.request.POST.get('manual_state') == 'done'
                                else OrderRefund.REFUND_STATE_CREATED
                            ),
                            amount=manual_value,
                            provider='manual'
                        ))

                offsetting_value = self.request.POST.get('refund-offsetting', '0') or '0'
                offsetting_value = formats.sanitize_separators(offsetting_value)
                try:
                    offsetting_value = Decimal(offsetting_value)
                except (DecimalException, TypeError):
                    messages.error(self.request, _('You entered an invalid number.'))
                    is_valid = False
                else:
                    if offsetting_value:
                        refund_selected += offsetting_value
                        try:
                            order = Order.objects.get(code=self.request.POST.get('order-offsetting'),
                                                      event__organizer=self.request.organizer)
                        except Order.DoesNotExist:
                            messages.error(self.request, _('You entered an order that could not be found.'))
                            is_valid = False
                        else:
                            refunds.append(OrderRefund(
                                order=self.order,
                                payment=None,
                                source=OrderRefund.REFUND_SOURCE_ADMIN,
                                state=OrderRefund.REFUND_STATE_DONE,
                                execution_date=now(),
                                amount=offsetting_value,
                                provider='offsetting',
                                info=json.dumps({
                                    'orders': [order.code]
                                })
                            ))

                for p in payments:
                    value = self.request.POST.get('refund-{}'.format(p.pk), '0') or '0'
                    value = formats.sanitize_separators(value)
                    try:
                        value = Decimal(value)
                    except (DecimalException, TypeError):
                        messages.error(self.request, _('You entered an invalid number.'))
                        is_valid = False
                    else:
                        if value == 0:
                            continue
                        elif value > p.available_amount:
                            messages.error(self.request, _('You can not refund more than the amount of a '
                                                           'payment that is not yet refunded.'))
                            is_valid = False
                            break
                        elif value != p.amount and not p.partial_refund_possible:
                            messages.error(self.request, _('You selected a partial refund for a payment method that '
                                                           'only supports full refunds.'))
                            is_valid = False
                            break
                        elif (p.partial_refund_possible or p.full_refund_possible) and value > 0:
                            refund_selected += value
                            refunds.append(OrderRefund(
                                order=self.order,
                                payment=p,
                                source=OrderRefund.REFUND_SOURCE_ADMIN,
                                state=OrderRefund.REFUND_STATE_CREATED,
                                amount=value,
                                provider=p.provider
                            ))

                any_success = False
                if refund_selected == full_refund and is_valid:
                    for r in refunds:
                        r.save()
                        self.order.log_action('pretix.event.order.refund.created', {
                            'local_id': r.local_id,
                            'provider': r.provider,
                        }, user=self.request.user)
                        if r.payment or r.provider == "offsetting":
                            try:
                                r.payment_provider.execute_refund(r)
                            except PaymentException as e:
                                r.state = OrderRefund.REFUND_STATE_FAILED
                                r.save()
                                messages.error(self.request, _('One of the refunds failed to be processed. You should '
                                                               'retry to refund in a different way. The error message '
                                                               'was: {}').format(str(e)))
                            else:
                                any_success = True
                                if r.state == OrderRefund.REFUND_STATE_DONE:
                                    messages.success(self.request, _('A refund of {} has been processed.').format(
                                        money_filter(r.amount, self.request.event.currency)
                                    ))
                                elif r.state == OrderRefund.REFUND_STATE_CREATED:
                                    messages.info(self.request, _('A refund of {} has been saved, but not yet '
                                                                  'fully executed. You can mark it as complete '
                                                                  'below.').format(
                                        money_filter(r.amount, self.request.event.currency)
                                    ))
                        else:
                            any_success = True

                    if any_success:
                        if self.start_form.cleaned_data.get('action') == 'mark_refunded':
                            mark_order_refunded(self.order, user=self.request.user)
                        elif self.start_form.cleaned_data.get('action') == 'mark_pending':
                            self.order.status = Order.STATUS_PENDING
                            self.order.set_expires(
                                now(),
                                self.order.event.subevents.filter(
                                    id__in=self.order.positions.values_list('subevent_id', flat=True))
                            )
                            self.order.save(update_fields=['status', 'expires'])

                    return redirect(self.get_order_url())
                else:
                    messages.error(self.request, _('The refunds you selected do not match the selected total refund '
                                                   'amount.'))

            return render(self.request, 'pretixcontrol/order/refund_choose.html', {
                'payments': payments,
                'remainder': to_refund,
                'order': self.order,
                'partial_amount': self.request.POST.get('start-partial_amount'),
                'start_form': self.start_form
            })
        return self.get(*args, **kwargs)

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/refund_start.html', {
            'form': self.start_form,
            'order': self.order,
        })


class OrderTransition(OrderView):
    permission = 'can_change_orders'

    @cached_property
    def mark_paid_form(self):
        return MarkPaidForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None,
        )

    def post(self, *args, **kwargs):
        to = self.request.POST.get('status', '')
        if self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and to == 'p' and self.mark_paid_form.is_valid():
            ps = self.mark_paid_form.cleaned_data['amount']
            try:
                p = self.order.payments.get(
                    state__in=(OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED),
                    provider='manual',
                    amount=ps
                )
            except OrderPayment.DoesNotExist:
                self.order.payments.filter(state__in=(OrderPayment.PAYMENT_STATE_PENDING,
                                                      OrderPayment.PAYMENT_STATE_CREATED)) \
                    .update(state=OrderPayment.PAYMENT_STATE_CANCELED)
                p = self.order.payments.create(
                    state=OrderPayment.PAYMENT_STATE_CREATED,
                    provider='manual',
                    amount=ps,
                    fee=None
                )

            try:
                p.confirm(user=self.request.user, count_waitinglist=False,
                          force=self.mark_paid_form.cleaned_data.get('force', False))
            except Quota.QuotaExceededException as e:
                p.state = OrderPayment.PAYMENT_STATE_FAILED
                p.save()
                self.order.log_action('pretix.event.order.payment.failed', {
                    'local_id': p.local_id,
                    'provider': p.provider,
                    'message': str(e)
                })
                messages.error(self.request, str(e))
            except PaymentException as e:
                p.state = OrderPayment.PAYMENT_STATE_FAILED
                p.save()
                self.order.log_action('pretix.event.order.payment.failed', {
                    'local_id': p.local_id,
                    'provider': p.provider,
                    'message': str(e)
                })
                messages.error(self.request, str(e))
            except SendMailException:
                messages.warning(self.request, _('The order has been marked as paid, but we were unable to send a '
                                                 'confirmation mail.'))
            else:
                messages.success(self.request, _('The payment has been created successfully.'))
        elif self.order.cancel_allowed() and to == 'c':
            cancel_order(self.order, user=self.request.user, send_mail=self.request.POST.get("send_email") == "on")
            messages.success(self.request, _('The order has been canceled.'))
        elif self.order.status == Order.STATUS_PENDING and to == 'e':
            mark_order_expired(self.order, user=self.request.user)
            messages.success(self.request, _('The order has been marked as expired.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        to = self.request.GET.get('status', '')
        if self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and to == 'p':
            return render(self.request, 'pretixcontrol/order/pay.html', {
                'form': self.mark_paid_form,
                'order': self.order,
            })
        elif self.order.cancel_allowed() and to == 'c':
            return render(self.request, 'pretixcontrol/order/cancel.html', {
                'order': self.order,
            })
        else:
            return HttpResponseNotAllowed(['POST'])


class OrderInvoiceCreate(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        has_inv = self.order.invoices.exists() and not (
            self.order.status in (Order.STATUS_PAID, Order.STATUS_PENDING)
            and self.order.invoices.filter(is_cancellation=True).count() >= self.order.invoices.filter(is_cancellation=False).count()
        )
        if self.request.event.settings.get('invoice_generate') not in ('admin', 'user', 'paid', 'True') or not invoice_qualified(self.order):
            messages.error(self.request, _('You cannot generate an invoice for this order.'))
        elif has_inv:
            messages.error(self.request, _('An invoice for this order already exists.'))
        else:
            inv = generate_invoice(self.order)
            self.order.log_action('pretix.event.order.invoice.generated', user=self.request.user, data={
                'invoice': inv.pk
            })
            messages.success(self.request, _('The invoice has been generated.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderCheckVATID(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            messages.error(self.request, _('No VAT ID specified.'))
            return redirect(self.get_order_url())
        else:
            if not ia.vat_id:
                messages.error(self.request, _('No VAT ID specified.'))
                return redirect(self.get_order_url())

            if not ia.country:
                messages.error(self.request, _('No country specified.'))
                return redirect(self.get_order_url())

            if str(ia.country) not in EU_COUNTRIES:
                messages.error(self.request, _('VAT ID could not be checked since a non-EU country has been '
                                               'specified.'))
                return redirect(self.get_order_url())

            if ia.vat_id[:2] != str(ia.country):
                messages.error(self.request, _('Your VAT ID does not match the selected country.'))
                return redirect(self.get_order_url())

            try:
                result = vat_moss.id.validate(ia.vat_id)
                if result:
                    country_code, normalized_id, company_name = result
                    ia.vat_id_validated = True
                    ia.vat_id = normalized_id
                    ia.save()
            except vat_moss.errors.InvalidError:
                messages.error(self.request, _('This VAT ID is not valid.'))
            except vat_moss.errors.WebServiceUnavailableError:
                logger.exception('VAT ID checking failed for country {}'.format(ia.country))
                messages.error(self.request, _('The VAT ID could not be checked, as the VAT checking service of '
                                               'the country is currently not available.'))
            else:
                messages.success(self.request, _('This VAT ID is valid.'))
            return redirect(self.get_order_url())

    def get(self, *args, **kwargs):  # NOQA
        return HttpResponseNotAllowed(['POST'])


class OrderInvoiceRegenerate(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            inv = self.order.invoices.get(pk=kwargs.get('id'))
        except Invoice.DoesNotExist:
            messages.error(self.request, _('Unknown invoice.'))
        else:
            if inv.canceled:
                messages.error(self.request, _('The invoice has already been canceled.'))
            elif inv.shredded:
                messages.error(self.request, _('The invoice has been cleaned of personal data.'))
            else:
                inv = regenerate_invoice(inv)
                self.order.log_action('pretix.event.order.invoice.regenerated', user=self.request.user, data={
                    'invoice': inv.pk
                })
                messages.success(self.request, _('The invoice has been regenerated.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):  # NOQA
        return HttpResponseNotAllowed(['POST'])


class OrderInvoiceReissue(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            inv = self.order.invoices.get(pk=kwargs.get('id'))
        except Invoice.DoesNotExist:
            messages.error(self.request, _('Unknown invoice.'))
        else:
            if inv.canceled:
                messages.error(self.request, _('The invoice has already been canceled.'))
            elif inv.shredded:
                messages.error(self.request, _('The invoice has been cleaned of personal data.'))
            else:
                c = generate_cancellation(inv)
                if self.order.status not in (Order.STATUS_CANCELED, Order.STATUS_REFUNDED):
                    inv = generate_invoice(self.order)
                else:
                    inv = c
                self.order.log_action('pretix.event.order.invoice.reissued', user=self.request.user, data={
                    'invoice': inv.pk
                })
                messages.success(self.request, _('The invoice has been reissued.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):  # NOQA
        return HttpResponseNotAllowed(['POST'])


class OrderResendLink(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        with language(self.order.locale):
            try:
                try:
                    invoice_name = self.order.invoice_address.name
                    invoice_company = self.order.invoice_address.company
                except InvoiceAddress.DoesNotExist:
                    invoice_name = ""
                    invoice_company = ""
                email_template = self.order.event.settings.mail_text_resend_link
                email_context = {
                    'event': self.order.event.name,
                    'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                        'order': self.order.code,
                        'secret': self.order.secret
                    }),
                    'invoice_name': invoice_name,
                    'invoice_company': invoice_company,
                }
                email_subject = _('Your order: %(code)s') % {'code': self.order.code}
                self.order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.resend', user=self.request.user,
                    attach_tickets=True
                )
            except SendMailException:
                messages.error(self.request, _('There was an error sending the mail. Please try again later.'))
                return redirect(self.get_order_url())

        messages.success(self.request, _('The email has been queued to be sent.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class InvoiceDownload(EventPermissionRequiredMixin, View):
    permission = 'can_view_orders'

    def get_order_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.invoice.order.code
        })

    def get(self, request, *args, **kwargs):
        try:
            self.invoice = Invoice.objects.get(
                event=self.request.event,
                id=self.kwargs['invoice']
            )
        except Invoice.DoesNotExist:
            raise Http404(_('This invoice has not been found'))

        if not self.invoice.file:
            invoice_pdf(self.invoice.pk)
            self.invoice = Invoice.objects.get(pk=self.invoice.pk)

        if self.invoice.shredded:
            messages.error(request, _('The invoice file is no longer stored on the server.'))
            return redirect(self.get_order_url())

        if not self.invoice.file:
            # This happens if we have celery installed and the file will be generated in the background
            messages.warning(request, _('The invoice file has not yet been generated, we will generate it for you '
                                        'now. Please try again in a few seconds.'))
            return redirect(self.get_order_url())

        try:
            resp = FileResponse(self.invoice.file.file, content_type='application/pdf')
        except FileNotFoundError:
            invoice_pdf_task.apply(args=(self.invoice.pk,))
            return self.get(request, *args, **kwargs)

        resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(self.invoice.number)
        return resp


class OrderExtend(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.form.is_valid():
            try:
                extend_order(
                    self.order,
                    new_date=self.form.cleaned_data.get('expires'),
                    force=self.form.cleaned_data.get('quota_ignore', False),
                    user=self.request.user
                )
                messages.success(self.request, _('The payment term has been changed.'))
            except OrderError as e:
                messages.error(self.request, str(e))
                return self._redirect_here()
            except LockTimeoutException:
                messages.error(self.request, _('We were not able to process the request completely as the '
                                               'server was too busy.'))
            return self._redirect_back()
        else:
            return self.get(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        return super().dispatch(request, *kwargs, **kwargs)

    def _redirect_here(self):
        return redirect('control:event.order.extend',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        code=self.order.code)

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/extend.html', {
            'order': self.order,
            'form': self.form,
        })

    @cached_property
    def form(self):
        return ExtendForm(instance=self.order,
                          data=self.request.POST if self.request.method == "POST" else None)


class OrderChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change.html'

    def dispatch(self, request, *args, **kwargs):
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
            messages.error(self.request, _('This action is only allowed for pending or paid orders.'))
            return self._redirect_back()
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def other_form(self):
        return OtherOperationsForm(prefix='other', order=self.order,
                                   data=self.request.POST if self.request.method == "POST" else None)

    @cached_property
    def add_form(self):
        return OrderPositionAddForm(prefix='add', order=self.order,
                                    data=self.request.POST if self.request.method == "POST" else None)

    @cached_property
    def positions(self):
        positions = list(self.order.positions.all())
        for p in positions:
            p.form = OrderPositionChangeForm(prefix='op-{}'.format(p.pk), instance=p,
                                             data=self.request.POST if self.request.method == "POST" else None)
            try:
                ia = self.order.invoice_address
            except InvoiceAddress.DoesNotExist:
                ia = None
            p.apply_tax = p.item.tax_rule and p.item.tax_rule.tax_applicable(invoice_address=ia)
        return positions

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['positions'] = self.positions
        ctx['add_form'] = self.add_form
        ctx['other_form'] = self.other_form
        return ctx

    def _process_other(self, ocm):
        if not self.other_form.is_valid():
            return False
        else:
            if self.other_form.cleaned_data['recalculate_taxes']:
                ocm.recalculate_taxes()
            return True

    def _process_add(self, ocm):
        if 'add-do' not in self.request.POST:
            return True
        if not self.add_form.is_valid():
            return False
        else:
            if self.add_form.cleaned_data['do']:
                if '-' in self.add_form.cleaned_data['itemvar']:
                    itemid, varid = self.add_form.cleaned_data['itemvar'].split('-')
                else:
                    itemid, varid = self.add_form.cleaned_data['itemvar'], None

                item = Item.objects.get(pk=itemid, event=self.request.event)
                if varid:
                    variation = ItemVariation.objects.get(pk=varid, item=item)
                else:
                    variation = None
                try:
                    ocm.add_position(item, variation,
                                     self.add_form.cleaned_data['price'],
                                     self.add_form.cleaned_data.get('addon_to'),
                                     self.add_form.cleaned_data.get('subevent'))
                except OrderError as e:
                    self.add_form.custom_error = str(e)
                    return False
        return True

    def _process_change(self, ocm):
        for p in self.positions:
            if not p.form.is_valid():
                return False

            try:
                if p.form.cleaned_data['operation'] == 'product':
                    if '-' in p.form.cleaned_data['itemvar']:
                        itemid, varid = p.form.cleaned_data['itemvar'].split('-')
                    else:
                        itemid, varid = p.form.cleaned_data['itemvar'], None

                    item = Item.objects.get(pk=itemid, event=self.request.event)
                    if varid:
                        variation = ItemVariation.objects.get(pk=varid, item=item)
                    else:
                        variation = None
                    ocm.change_item(p, item, variation)
                elif p.form.cleaned_data['operation'] == 'price':
                    ocm.change_price(p, p.form.cleaned_data['price'])
                elif p.form.cleaned_data['operation'] == 'subevent':
                    ocm.change_subevent(p, p.form.cleaned_data['subevent'])
                elif p.form.cleaned_data['operation'] == 'cancel':
                    ocm.cancel(p)
                elif p.form.cleaned_data['operation'] == 'split':
                    ocm.split(p)
                elif p.form.cleaned_data['operation'] == 'secret':
                    ocm.regenerate_secret(p)

            except OrderError as e:
                p.custom_error = str(e)
                return False
        return True

    def post(self, *args, **kwargs):
        notify = self.other_form.cleaned_data['notify'] if self.other_form.is_valid() else True
        ocm = OrderChangeManager(
            self.order,
            user=self.request.user,
            notify=notify
        )
        form_valid = self._process_add(ocm) and self._process_change(ocm) and self._process_other(ocm)

        if not form_valid:
            messages.error(self.request, _('An error occurred. Please see the details below.'))
        else:
            try:
                ocm.commit()
            except OrderError as e:
                messages.error(self.request, str(e))
            else:
                if notify:
                    messages.success(self.request, _('The order has been changed and the user has been notified.'))
                else:
                    messages.success(self.request, _('The order has been changed.'))
                return self._redirect_back()

        return self.get(*args, **kwargs)


class OrderModifyInformation(OrderQuestionsViewMixin, OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_questions.html'
    only_user_visible = False

    def post(self, request, *args, **kwargs):
        failed = not self.save() or not self.invoice_form.is_valid()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(request, *args, **kwargs)
        self.invoice_form.save()
        self.order.log_action('pretix.event.order.modified', {
            'invoice_data': self.invoice_form.cleaned_data,
            'data': [{
                k: (f.cleaned_data.get(k).name if isinstance(f.cleaned_data.get(k), File) else f.cleaned_data.get(k))
                for k in f.changed_data
            } for f in self.forms]
        }, user=request.user)
        if self.invoice_form.has_changed():
            success_message = ('The invoice address has been updated. If you want to generate a new invoice, '
                               'you need to do this manually.')
            messages.success(self.request, _(success_message))

        CachedTicket.objects.filter(order_position__order=self.order).delete()
        CachedCombinedTicket.objects.filter(order=self.order).delete()
        return redirect(self.get_order_url())


class OrderContactChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_contact.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['form'] = self.form
        return ctx

    @cached_property
    def form(self):
        return OrderContactForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None
        )

    def post(self, *args, **kwargs):
        old_email = self.order.email
        changed = False
        if self.form.is_valid():
            new_email = self.form.cleaned_data['email']
            if new_email != old_email:
                changed = True
                self.order.log_action(
                    'pretix.event.order.contact.changed',
                    data={
                        'old_email': old_email,
                        'new_email': self.form.cleaned_data['email'],
                    },
                    user=self.request.user,
                )
            if self.form.cleaned_data['regenerate_secrets']:
                changed = True
                self.order.secret = generate_secret()
                for op in self.order.positions.all():
                    op.secret = generate_position_secret()
                    op.save()
                CachedTicket.objects.filter(order_position__order=self.order).delete()
                CachedCombinedTicket.objects.filter(order=self.order).delete()
                self.order.log_action('pretix.event.order.secret.changed', user=self.request.user)

            self.form.save()
            if changed:
                messages.success(self.request, _('The order has been changed.'))
            else:
                messages.success(self.request, _('Nothing about the order had to be changed.'))
            return redirect(self.get_order_url())
        return self.get(*args, **kwargs)


class OrderLocaleChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_locale.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['form'] = self.form
        return ctx

    @cached_property
    def form(self):
        return OrderLocaleForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None
        )

    def post(self, *args, **kwargs):
        old_locale = self.order.locale
        if self.form.is_valid():
            self.order.log_action(
                'pretix.event.order.locale.changed',
                data={
                    'old_locale': old_locale,
                    'new_locale': self.form.cleaned_data['locale'],
                },
                user=self.request.user,
            )

            self.form.save()
            messages.success(self.request, _('The order has been changed.'))
            return redirect(self.get_order_url())
        return self.get(*args, **kwargs)


class OrderViewMixin:
    def get_object(self, queryset=None):
        try:
            return Order.objects.get(
                event=self.request.event,
                code=self.kwargs['code'].upper()
            )
        except Order.DoesNotExist:
            raise Http404()

    @cached_property
    def order(self):
        return self.get_object()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


class OrderSendMail(EventPermissionRequiredMixin, OrderViewMixin, FormView):
    template_name = 'pretixcontrol/order/sendmail.html'
    permission = 'can_change_orders'
    form_class = OrderMailForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['order'] = Order.objects.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not send the email. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        tz = pytz.timezone(self.request.event.settings.timezone)
        order = Order.objects.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )
        self.preview_output = {}
        try:
            invoice_name = order.invoice_address.name
            invoice_company = order.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""
        with language(order.locale):
            email_context = {
                'event': order.event,
                'code': order.code,
                'date': date_format(order.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                'expire_date': date_format(order.expires, 'SHORT_DATE_FORMAT'),
                'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }),
                'invoice_name': invoice_name,
                'invoice_company': invoice_company,
            }
        email_template = LazyI18nString(form.cleaned_data['message'])
        email_content = render_mail(email_template, email_context)
        if self.request.POST.get('action') == 'preview':
            self.preview_output = []
            self.preview_output.append(
                _('Subject: {subject}').format(subject=form.cleaned_data['subject']))
            self.preview_output.append(email_content)
            return self.get(self.request, *self.args, **self.kwargs)
        else:
            try:
                order.send_mail(
                    form.cleaned_data['subject'], email_template,
                    email_context, 'pretix.event.order.email.custom_sent',
                    self.request.user
                )
                messages.success(self.request,
                                 _('Your message has been queued and will be sent to {}.'.format(order.email)))
            except SendMailException:
                messages.error(
                    self.request,
                    _('Failed to send mail to the following user: {}'.format(order.email))
                )
            return super(OrderSendMail, self).form_valid(form)

    def get_success_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.kwargs['code']
        })

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['preview_output'] = getattr(self, 'preview_output', None)
        return ctx


class OrderEmailHistory(EventPermissionRequiredMixin, OrderViewMixin, ListView):
    template_name = 'pretixcontrol/order/mail_history.html'
    permission = 'can_view_orders'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 10

    def get_queryset(self):
        order = Order.objects.filter(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        ).first()
        qs = order.all_logentries()
        qs = qs.filter(
            action_type__contains="order.email"
        )
        return qs


class AnswerDownload(EventPermissionRequiredMixin, OrderViewMixin, ListView):
    permission = 'can_view_orders'

    def get(self, request, *args, **kwargs):
        answid = kwargs.get('answer')
        token = request.GET.get('token', '')

        answer = get_object_or_404(QuestionAnswer, orderposition__order=self.order, id=answid)
        if not answer.file:
            raise Http404()
        if not check_token(request, answer, token):
            raise Http404(_("This link is no longer valid. Please go back, refresh the page, and try again."))

        ftype, ignored = mimetypes.guess_type(answer.file.name)
        resp = FileResponse(answer.file, content_type=ftype or 'application/binary')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}-{}"'.format(
            self.request.event.slug.upper(), self.order.code,
            answer.orderposition.positionid,
            os.path.basename(answer.file.name).split('.', 1)[1]
        )
        return resp


class OverView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/overview.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        subevent = None
        if self.request.GET.get("subevent", "") != "" and self.request.event.has_subevents:
            i = self.request.GET.get("subevent", "")
            try:
                subevent = self.request.event.subevents.get(pk=i)
            except SubEvent.DoesNotExist:
                pass

        ctx['items_by_category'], ctx['total'] = order_overview(self.request.event, subevent=subevent)
        ctx['subevent_warning'] = self.request.event.has_subevents and subevent and (
            OrderFee.objects.filter(order__event=self.request.event).exclude(value=0).exists()
        )
        return ctx


class OrderGo(EventPermissionRequiredMixin, View):
    permission = 'can_view_orders'

    def get_order(self, code):
        try:
            return Order.objects.get(code=code, event=self.request.event)
        except Order.DoesNotExist:
            return Order.objects.get(code=Order.normalize_code(code), event=self.request.event)

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").upper().strip()
        try:
            if code.startswith(request.event.slug.upper()):
                code = code[len(request.event.slug):]
            if code.startswith('-'):
                code = code[1:]
            order = self.get_order(code)
            return redirect('control:event.order', event=request.event.slug, organizer=request.event.organizer.slug,
                            code=order.code)
        except Order.DoesNotExist:
            messages.error(request, _('There is no order with the given order code.'))
            return redirect('control:event.orders', event=request.event.slug, organizer=request.event.organizer.slug)


class ExportMixin:
    @cached_property
    def exporters(self):
        exporters = []
        responses = register_data_exporters.send(self.request.event)
        for receiver, response in responses:
            ex = response(self.request.event)
            if self.request.GET.get("identifier") and ex.identifier != self.request.GET.get("identifier"):
                continue

            # Use form parse cycle to generate useful defaults
            test_form = ExporterForm(data=self.request.GET, prefix=ex.identifier)
            test_form.fields = ex.export_form_fields
            test_form.is_valid()
            initial = {
                k: v for k, v in test_form.cleaned_data.items() if ex.identifier + "-" + k in self.request.GET
            }

            ex.form = ExporterForm(
                data=(self.request.POST if self.request.method == 'POST' else None),
                prefix=ex.identifier,
                initial=initial
            )
            ex.form.fields = ex.export_form_fields
            exporters.append(ex)
        return exporters


class ExportDoView(EventPermissionRequiredMixin, ExportMixin, AsyncAction, View):
    permission = 'can_view_orders'
    task = export

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return reverse('cachedfile.download', kwargs={'id': str(value)})

    def get_error_url(self):
        return reverse('control:event.orders.export', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    @cached_property
    def exporter(self):
        for ex in self.exporters:
            if ex.identifier == self.request.POST.get("exporter"):
                return ex

    def post(self, request, *args, **kwargs):
        if not self.exporter:
            messages.error(self.request, _('The selected exporter was not found.'))
            return redirect('control:event.orders.export', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            })

        if not self.exporter.form.is_valid():
            messages.error(self.request, _('There was a problem processing your input. See below for error details.'))
            return self.get(request, *args, **kwargs)

        cf = CachedFile()
        cf.date = now()
        cf.expires = now() + timedelta(days=3)
        cf.save()
        return self.do(self.request.event.id, str(cf.id), self.exporter.identifier, self.exporter.form.cleaned_data)


class ExportView(EventPermissionRequiredMixin, ExportMixin, TemplateView):
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/orders/export.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exporters'] = self.exporters
        return ctx


class RefundList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = OrderRefund
    context_object_name = 'refunds'
    template_name = 'pretixcontrol/orders/refunds.html'
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = OrderRefund.objects.filter(
            order__event=self.request.event
        ).select_related('order')

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return RefundFilterForm(data=self.request.GET, event=self.request.event,
                                initial={'status': 'open'})
