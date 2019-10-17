import inspect
import mimetypes
import os
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.files import File
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView, View

from pretix.base.models import (
    CachedTicket, Invoice, Order, OrderPosition, Quota,
)
from pretix.base.models.orders import (
    CachedCombinedTicket, OrderFee, OrderPayment, OrderRefund, QuestionAnswer,
)
from pretix.base.payment import PaymentException
from pretix.base.services.invoices import (
    generate_invoice, invoice_pdf, invoice_pdf_task, invoice_qualified,
)
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import cancel_order, change_payment_provider
from pretix.base.services.tickets import generate, invalidate_cache
from pretix.base.signals import (
    allow_ticket_download, order_modified, register_ticket_outputs,
)
from pretix.base.views.mixins import OrderQuestionsViewMixin
from pretix.base.views.tasks import AsyncAction
from pretix.helpers.safedownload import check_token
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.presale.forms.checkout import InvoiceAddressForm, QuestionsForm
from pretix.presale.views import (
    CartMixin, EventViewMixin, iframe_entry_view_wrapper,
)
from pretix.presale.views.robots import NoSearchIndexViewMixin


class OrderDetailMixin(NoSearchIndexViewMixin):

    @cached_property
    def order(self):
        order = self.request.event.orders.filter(code=self.kwargs['order']).select_related('event').first()
        if order:
            if order.secret.lower() == self.kwargs['secret'].lower():
                return order
            else:
                return None
        else:
            # Do a comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == self.kwargs['secret'].lower():
                return None
            else:
                return None

    def get_order_url(self):
        return eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderPositionDetailMixin(NoSearchIndexViewMixin):
    @cached_property
    def position(self):
        p = OrderPosition.objects.filter(
            order__event=self.request.event,
            addon_to__isnull=True,
            order__code=self.kwargs['order'],
            positionid=self.kwargs['position']
        ).select_related('order', 'order__event').first()
        if p:
            if p.web_secret.lower() == self.kwargs['secret'].lower():
                return p
            else:
                return None
        else:
            # Do a comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == self.kwargs['secret'].lower():
                return None
            else:
                return None

    @cached_property
    def order(self):
        return self.position.order if self.position else None

    def get_position_url(self):
        return eventreverse(self.request.event, 'presale:event.order.position', kwargs={
            'order': self.order.code,
            'secret': self.position.web_secret,
            'position': self.position.positionid,
        })


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderOpen(EventViewMixin, OrderDetailMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if kwargs.get('hash') == self.order.email_confirm_hash():
            self.order.email_known_to_work = True
            self.order.save(update_fields=['email_known_to_work'])
        return redirect(self.get_order_url())


class TicketPageMixin:

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['order'] = self.order

        can_download = all([r for rr, r in allow_ticket_download.send(self.request.event, order=self.order)])
        if self.request.event.settings.ticket_download_date:
            ctx['ticket_download_date'] = self.order.ticket_download_date
        ctx['can_download'] = can_download and self.order.ticket_download_available and self.order.positions_with_tickets
        ctx['download_buttons'] = self.download_buttons

        ctx['backend_user'] = (
            self.request.user.is_authenticated
            and self.request.user.has_event_permission(self.request.organizer, self.request.event, 'can_view_orders', request=self.request)
        )
        return ctx


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderDetails(EventViewMixin, OrderDetailMixin, CartMixin, TicketPageMixin, TemplateView):
    template_name = "pretixpresale/event/order.html"

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        return super().get(request, *args, **kwargs)

    @cached_property
    def download_buttons(self):
        buttons = []

        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if not provider.is_enabled:
                continue
            buttons.append({
                'text': provider.download_button_text or 'Download',
                'icon': provider.download_button_icon or 'fa-download',
                'identifier': provider.identifier,
                'multi': provider.multi_download_enabled
            })
        return buttons

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cart'] = self.get_cart(
            answers=True, downloads=ctx['can_download'],
            queryset=self.order.positions.prefetch_related('issued_gift_cards').select_related('tax_rule'),
            order=self.order
        )
        ctx['can_download_multi'] = any([b['multi'] for b in self.download_buttons]) and (
            [p.generate_ticket for p in ctx['cart']['positions']].count(True) > 1
        )
        ctx['invoices'] = list(self.order.invoices.all())
        can_generate_invoice = (
            self.order.sales_channel in self.request.event.settings.get('invoice_generate_sales_channels')
            and (
                self.request.event.settings.get('invoice_generate') in ('user', 'True')
                or (
                    self.request.event.settings.get('invoice_generate') == 'paid'
                    and self.order.status == Order.STATUS_PAID
                )
            )
        )
        ctx['can_generate_invoice'] = invoice_qualified(self.order) and can_generate_invoice
        ctx['url'] = build_absolute_uri(
            self.request.event, 'presale:event.order', kwargs={
                'order': self.order.code,
                'secret': self.order.secret
            }
        )
        ctx['invoice_address_asked'] = self.request.event.settings.invoice_address_asked and (
            self.order.total != Decimal('0.00') or not self.request.event.settings.invoice_address_not_asked_free
        )

        if self.order.status == Order.STATUS_PENDING:
            ctx['pending_sum'] = self.order.pending_sum
            ctx['payment_sum_neg'] = ctx['pending_sum'] - self.order.total

            lp = self.order.payments.last()
            ctx['can_pay'] = False

            for provider in self.request.event.get_payment_providers().values():
                if provider.is_enabled and provider.order_change_allowed(self.order):
                    ctx['can_pay'] = True
                    break

            if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED):
                ctx['last_payment'] = self.order.payments.last()

                pp = lp.payment_provider
                ctx['last_payment_info'] = pp.payment_pending_render(self.request, ctx['last_payment'])

                if lp.state == OrderPayment.PAYMENT_STATE_PENDING and not pp.abort_pending_allowed:
                    ctx['can_pay'] = False

            ctx['can_pay'] = ctx['can_pay'] and self.order._can_be_paid() is True

        elif self.order.status == Order.STATUS_PAID:
            ctx['can_pay'] = False

        ctx['refunds'] = self.order.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT, OrderRefund.REFUND_STATE_CREATED)
        )

        return ctx


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderPositionDetails(EventViewMixin, OrderPositionDetailMixin, CartMixin, TicketPageMixin, TemplateView):
    template_name = "pretixpresale/event/position.html"

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.position:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        return super().get(request, *args, **kwargs)

    @cached_property
    def download_buttons(self):
        buttons = []

        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if not provider.is_enabled:
                continue
            buttons.append({
                'text': provider.download_button_text or 'Download',
                'icon': provider.download_button_icon or 'fa-download',
                'identifier': provider.identifier,
                'multi': provider.multi_download_enabled
            })
        return buttons

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_download_multi'] = False
        ctx['position'] = self.position
        ctx['cart'] = self.get_cart(
            answers=True, downloads=ctx['can_download'],
            queryset=self.order.positions.select_related('tax_rule').filter(
                Q(pk=self.position.pk) | Q(addon_to__id=self.position.pk)
            ),
            order=self.order
        )
        return ctx


@method_decorator(xframe_options_exempt, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class OrderPaymentStart(EventViewMixin, OrderDetailMixin, TemplateView):
    """
    This is used if a payment is retried or the payment method is changed. It shows the payment
    provider's form that asks for payment details (e.g. CC number).
    """
    template_name = "pretixpresale/event/order_pay.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if (self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED)
                or self.payment.state != OrderPayment.PAYMENT_STATE_CREATED
                or not self.payment.payment_provider.is_enabled
                or self.order._can_be_paid() is not True):
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())

        term_last = self.order.payment_term_last
        if term_last and now() > term_last:
            messages.error(request, _('The payment is too late to be accepted.'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = self.payment.payment_provider.payment_prepare(request, self.payment)
        if 'payment_change_{}'.format(self.order.pk) in request.session:
            del request.session['payment_change_{}'.format(self.order.pk)]
        if isinstance(resp, str):
            return redirect(resp)
        elif resp is True:
            return redirect(self.get_confirm_url())
        else:
            return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['form'] = self.form
        ctx['provider'] = self.payment.payment_provider
        return ctx

    @cached_property
    def form(self):
        if 'total' in inspect.signature(self.payment.payment_provider.payment_form_render).parameters:
            return self.payment.payment_provider.payment_form_render(self.request, self.payment.amount)
        else:
            return self.payment.payment_provider.payment_form_render(self.request)

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments, pk=self.kwargs['payment'])

    def get_confirm_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay.confirm', kwargs={
            'order': self.order.code,
            'secret': self.order.secret,
            'payment': self.payment.pk
        })


@method_decorator(xframe_options_exempt, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class OrderPaymentConfirm(EventViewMixin, OrderDetailMixin, TemplateView):
    """
    This is used if a payment is retried or the payment method is changed. It is shown after the
    payment details have been entered and allows the user to confirm and review the details. On
    submitting this view, the payment is performed.
    """
    template_name = "pretixpresale/event/order_pay_confirm.html"

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments, pk=self.kwargs['payment'])

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.payment.state != OrderPayment.PAYMENT_STATE_CREATED or not self.order._can_be_paid():
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())
        if (not self.payment.payment_provider.payment_is_valid_session(request) or
                not self.payment.payment_provider.is_enabled):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())

        term_last = self.order.payment_term_last
        if term_last and now() > term_last:
            messages.error(request, _('The payment is too late to be accepted.'))
            return redirect(self.get_order_url())

        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            resp = self.payment.payment_provider.execute_payment(request, self.payment)
        except PaymentException as e:
            messages.error(request, str(e))
            return redirect(self.get_order_url())
        if 'payment_change_{}'.format(self.order.pk) in request.session:
            del request.session['payment_change_{}'.format(self.order.pk)]
        return redirect(resp or self.get_order_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['payment'] = self.payment
        ctx['payment_info'] = self.payment.payment_provider.checkout_confirm_render(self.request)
        ctx['payment_provider'] = self.payment.payment_provider
        return ctx

    def get_payment_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'secret': self.order.secret,
            'payment': self.payment.pk
        })


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderPaymentComplete(EventViewMixin, OrderDetailMixin, View):
    """
    This is used for the first try of a payment. This means the user just entered payment
    details and confirmed them during the order process and we don't need to show them again,
    we just need to perform the payment.
    """

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments, pk=self.kwargs['payment'])

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.payment.state != OrderPayment.PAYMENT_STATE_CREATED or not self.order._can_be_paid():
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())
        if (not self.payment.payment_provider.payment_is_valid_session(request) or
                not self.payment.payment_provider.is_enabled):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())

        term_last = self.order.payment_term_last
        if term_last and now() > term_last:
            messages.error(request, _('The payment is too late to be accepted.'))
            return redirect(self.get_order_url())

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        try:
            resp = self.payment.payment_provider.execute_payment(request, self.payment)
        except PaymentException as e:
            messages.error(request, str(e))
            return redirect(self.get_order_url())

        if self.order.status == Order.STATUS_PAID:
            return redirect(resp or self.get_order_url() + '?paid=yes')
        else:
            return redirect(resp or self.get_order_url() + '?thanks=yes')

    def get_payment_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'payment': self.payment.pk,
            'secret': self.order.secret
        })


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderPayChangeMethod(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = 'pretixpresale/event/order_pay_change.html'

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) or not self.order._can_be_paid():
            messages.error(request, _('The payment method for this order cannot be changed.'))
            return redirect(self.get_order_url())

        term_last = self.order.payment_term_last
        if term_last and now() > term_last:
            messages.error(request, _('The payment is too late to be accepted.'))
            return redirect(self.get_order_url())

        if self.open_payment:
            pp = self.open_payment.payment_provider
            if self.open_payment.state == OrderPayment.PAYMENT_STATE_PENDING and not pp.abort_pending_allowed:
                messages.error(request, _('A payment is currently pending for this order.'))
                return redirect(self.get_order_url())

        return super().dispatch(request, *args, **kwargs)

    def get_payment_url(self, payment):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'secret': self.order.secret,
            'payment': payment.pk
        })

    @cached_property
    def open_fees(self):
        e = OrderPayment.objects.filter(
            fee=OuterRef('pk'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
        )
        return self.order.fees.annotate(has_p=Exists(e)).filter(
            Q(fee_type=OrderFee.FEE_TYPE_PAYMENT) & ~Q(has_p=True)
        )

    @cached_property
    def open_payment(self):
        lp = self.order.payments.last()
        if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED):
            return lp
        return None

    @cached_property
    def _position_sum(self):
        return self.order.positions.aggregate(sum=Sum('price'))['sum'] or Decimal('0.00')

    @transaction.atomic()
    def mark_paid_free(self):
        p = self.order.payments.create(
            state=OrderPayment.PAYMENT_STATE_CREATED,
            provider='manual',
            amount=Decimal('0.00'),
            fee=None
        )
        try:
            p.confirm()
        except SendMailException:
            pass

    def get(self, request, *args, **kwargs):
        if self.order.pending_sum <= Decimal('0.00'):
            try:
                self.mark_paid_free()
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
                return redirect(self.get_order_url())
            except PaymentException as e:
                messages.error(self.request, str(e))
                return redirect(self.get_order_url())
            else:
                return redirect(self.get_order_url() + '?paid=1')
        return super().get(request, *args, **kwargs)

    @cached_property
    def provider_forms(self):
        providers = []
        pending_sum = self.order.pending_sum
        for provider in self.request.event.get_payment_providers().values():
            if not provider.is_enabled or not provider.order_change_allowed(self.order):
                continue
            current_fee = sum(f.value for f in self.open_fees) or Decimal('0.00')
            fee = provider.calculate_fee(pending_sum - current_fee)
            if 'total' in inspect.signature(provider.payment_form_render).parameters:
                form = provider.payment_form_render(self.request, abs(pending_sum + fee - current_fee))
            else:
                form = provider.payment_form_render(self.request)
            providers.append({
                'provider': provider,
                'fee': fee,
                'fee_diff': fee - current_fee,
                'fee_diff_abs': abs(fee - current_fee),
                'total': abs(pending_sum + fee - current_fee),
                'form': form
            })
        return providers

    def post(self, request, *args, **kwargs):
        self.request = request
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                request.session['payment'] = p['provider'].identifier
                request.session['payment_change_{}'.format(self.order.pk)] = '1'

                with transaction.atomic():
                    old_fee, new_fee, fee, newpayment = change_payment_provider(self.order, p['provider'], None)

                resp = p['provider'].payment_prepare(request, newpayment)
                if isinstance(resp, str):
                    return redirect(resp)
                elif resp is True:
                    return redirect(self.get_confirm_url(newpayment))
                else:
                    return self.get(request, *args, **kwargs)
        messages.error(self.request, _("Please select a payment method."))
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['providers'] = self.provider_forms
        ctx['show_fees'] = any(p['fee_diff'] for p in self.provider_forms)
        return ctx

    def get_confirm_url(self, payment):
        return eventreverse(self.request.event, 'presale:event.order.pay.confirm', kwargs={
            'order': self.order.code,
            'secret': self.order.secret,
            'payment': payment.pk
        })


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderInvoiceCreate(EventViewMixin, OrderDetailMixin, View):

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        can_generate_invoice = (
            self.order.sales_channel in self.request.event.settings.get('invoice_generate_sales_channels')
            and (
                self.request.event.settings.get('invoice_generate') in ('user', 'True')
                or (
                    self.request.event.settings.get('invoice_generate') == 'paid'
                    and self.order.status == Order.STATUS_PAID
                )
            )
        )
        if not can_generate_invoice or not invoice_qualified(self.order):
            messages.error(self.request, _('You cannot generate an invoice for this order.'))
        elif self.order.invoices.exists():
            messages.error(self.request, _('An invoice for this order already exists.'))
        else:
            i = generate_invoice(self.order)
            self.order.log_action('pretix.event.order.invoice.generated', data={
                'invoice': i.pk
            })
            messages.success(self.request, _('The invoice has been generated.'))
        return redirect(self.get_order_url())


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderModify(EventViewMixin, OrderDetailMixin, OrderQuestionsViewMixin, TemplateView):
    form_class = QuestionsForm
    invoice_form_class = InvoiceAddressForm
    template_name = "pretixpresale/event/order_modify.html"

    def post(self, request, *args, **kwargs):
        failed = not self.save() or not self.invoice_form.is_valid()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(request, *args, **kwargs)
        if hasattr(self.invoice_form, 'save'):
            self.invoice_form.save()
        self.order.log_action('pretix.event.order.modified', {
            'invoice_data': self.invoice_form.cleaned_data,
            'data': [{
                k: (f.cleaned_data.get(k).name
                    if isinstance(f.cleaned_data.get(k), File)
                    else f.cleaned_data.get(k))
                for k in f.changed_data
            } for f in self.forms]
        })
        order_modified.send(sender=self.request.event, order=self.order)
        if self.invoice_form.has_changed():
            messages.success(self.request, _('Your invoice address has been updated. Please contact us if you need us '
                                             'to regenerate your invoice.'))
        else:
            messages.success(self.request, _('Your changes have been saved.'))

        invalidate_cache.apply_async(kwargs={'event': self.request.event.pk, 'order': self.order.pk})
        CachedTicket.objects.filter(order_position__order=self.order).delete()
        CachedCombinedTicket.objects.filter(order=self.order).delete()
        return redirect(self.get_order_url())

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if not self.order.can_modify_answers:
            messages.error(request, _('You cannot modify this order'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderCancel(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_cancel.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if not self.order.user_cancel_allowed:
            messages.error(request, _('You cannot cancel this order.'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        refund_amount = self.order.payment_refund_sum - self.order.user_cancel_fee
        proposals = self.order.propose_auto_refunds(refund_amount)
        ctx['refund_amount'] = refund_amount
        ctx['can_auto_refund'] = sum(proposals.values()) == refund_amount
        return ctx


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderCancelDo(EventViewMixin, OrderDetailMixin, AsyncAction, View):
    task = cancel_order
    known_errortypes = ['OrderError']

    def get_success_url(self, value):
        return self.get_order_url()

    def get_error_url(self):
        return self.get_order_url()

    def post(self, request, *args, **kwargs):
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if not self.order.user_cancel_allowed:
            messages.error(request, _('You cannot cancel this order.'))
            return redirect(self.get_order_url())
        fee = None
        if self.order.status == Order.STATUS_PAID and self.order.total != Decimal('0.00'):
            fee = self.order.user_cancel_fee
        return self.do(self.order.pk, cancellation_fee=fee, try_auto_refund=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx

    def get_success_message(self, value):
        return _('The order has been canceled.')


@method_decorator(xframe_options_exempt, 'dispatch')
class AnswerDownload(EventViewMixin, OrderDetailMixin, View):
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


class OrderDownloadMixin:
    def get_success_url(self, value):
        return self.get_self_url()

    @cached_property
    def output(self):
        if not all([r for rr, r in allow_ticket_download.send(self.request.event, order=self.order)]):
            return None
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.kwargs.get('output'):
                return provider

    def get(self, request, *args, **kwargs):
        if not self.output or not self.output.is_enabled:
            return self.error(_('You requested an invalid ticket output type.'))
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        ct = self.get_last_ct()
        if ct:
            return self.success(ct)
        return self.http_method_not_allowed(request)

    def post(self, request, *args, **kwargs):
        if not self.output or not self.output.is_enabled:
            return self.error(_('You requested an invalid ticket output type.'))
        if not self.order or ('position' in kwargs and not self.order_position):
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if not self.order.ticket_download_available:
            return self.error(_('Ticket download is not (yet) enabled for this order.'))
        if 'position' in kwargs and not self.order_position.generate_ticket:
            return self.error(_('Ticket download is not enabled for this product.'))

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


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderDownload(OrderDownloadMixin, EventViewMixin, OrderDetailMixin, AsyncAction, View):
    task = generate

    def get_error_url(self):
        return self.get_order_url()

    def get_self_url(self):
        return eventreverse(self.request.event,
                            'presale:event.order.download' if 'position' in self.kwargs
                            else 'presale:event.order.download.combined',
                            kwargs=self.kwargs)

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(pk=self.kwargs.get('position'))
        except OrderPosition.DoesNotExist:
            return None


@method_decorator(xframe_options_exempt, 'dispatch')
class OrderPositionDownload(OrderDownloadMixin, EventViewMixin, OrderPositionDetailMixin, AsyncAction, View):
    task = generate

    def get_error_url(self):
        return self.get_position_url()

    def get_self_url(self):
        return eventreverse(self.request.event,
                            'presale:event.order.position.download',
                            kwargs=self.kwargs)

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(
                Q(pk=self.kwargs.get('pid')) & Q(
                    Q(pk=self.position.pk) | Q(addon_to__id=self.position.pk)
                )
            )
        except OrderPosition.DoesNotExist:
            return None


@method_decorator(xframe_options_exempt, 'dispatch')
class InvoiceDownload(EventViewMixin, OrderDetailMixin, View):

    def get(self, request, *args, **kwargs):
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))

        try:
            invoice = Invoice.objects.get(
                event=self.request.event,
                order=self.order,
                id=self.kwargs['invoice']
            )
        except Invoice.DoesNotExist:
            raise Http404(_('This invoice has not been found'))

        if not invoice.file:
            invoice_pdf(invoice.pk)
            invoice = Invoice.objects.get(pk=invoice.pk)

        if invoice.shredded:
            messages.error(request, _('The invoice file is no longer stored on the server.'))
            return redirect(self.get_order_url())

        if not invoice.file:
            # This happens if we have celery installed and the file will be generated in the background
            messages.warning(request, _('The invoice file has not yet been generated, we will generate it for you '
                                        'now. Please try again in a few seconds.'))
            return redirect(self.get_order_url())

        try:
            resp = FileResponse(invoice.file.file, content_type='application/pdf')
        except FileNotFoundError:
            invoice_pdf_task.apply(args=(invoice.pk,))
            return self.get(request, *args, **kwargs)
        resp['Content-Disposition'] = 'inline; filename="{}.pdf"'.format(invoice.number)
        resp._csp_ignore = True  # Some browser's PDF readers do not work with CSP
        return resp
