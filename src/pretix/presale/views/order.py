from datetime import timedelta

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext, ugettext_lazy as _
from django.views.generic import TemplateView, View

from pretix.base.models import (
    CachedFile, CachedTicket, Invoice, Order, OrderPosition,
)
from pretix.base.models.orders import InvoiceAddress
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
)
from pretix.base.services.orders import OrderError, cancel_order
from pretix.base.services.tickets import generate
from pretix.base.signals import (
    register_payment_providers, register_ticket_outputs,
)
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.forms.checkout import InvoiceAddressForm
from pretix.presale.views import CartMixin, EventViewMixin
from pretix.presale.views.async import AsyncAction
from pretix.presale.views.questions import QuestionsViewMixin


class OrderDetailMixin:
    @cached_property
    def order(self):
        try:
            return Order.objects.get(secret=self.kwargs['secret'],
                                     event=self.request.event, code=self.kwargs['order'])
        except Order.DoesNotExist:
            return None

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider

    def get_order_url(self):
        return eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderDetails(EventViewMixin, OrderDetailMixin, CartMixin, TemplateView):
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
                'icon': provider.download_button_icon or 'fa-download',
                'text': provider.download_button_text or 'fa-download',
                'identifier': provider.identifier,
            })
        return buttons

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['can_download'] = (
            self.request.event.settings.ticket_download
            and (
                self.request.event.settings.ticket_download_date is None
                or now() > self.request.event.settings.ticket_download_date
            ) and self.order.status == Order.STATUS_PAID
        )
        ctx['download_buttons'] = self.download_buttons
        ctx['cart'] = self.get_cart(
            answers=True,
            queryset=OrderPosition.objects.filter(order=self.order),
            payment_fee=self.order.payment_fee, payment_fee_tax_rate=self.order.payment_fee_tax_rate
        )
        ctx['invoices'] = list(self.order.invoices.all())
        ctx['can_generate_invoice'] = invoice_qualified(self.order) and (
            self.request.event.settings.invoice_generate == 'user'
        )

        if self.order.status == Order.STATUS_PENDING:
            ctx['payment'] = self.payment_provider.order_pending_render(self.request, self.order)
            ctx['can_retry'] = (
                self.payment_provider.order_can_retry(self.order)
                and self.payment_provider.is_enabled
                and self.order._can_be_paid()
            )
        elif self.order.status == Order.STATUS_PAID:
            ctx['payment'] = self.payment_provider.order_paid_render(self.request, self.order)
            ctx['can_retry'] = False
        return ctx


class OrderPay(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_pay.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if (self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED)
                or not self.payment_provider.order_can_retry(self.order)
                or not self.payment_provider.is_enabled):
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url() + '?paid=yes')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = self.payment_provider.order_prepare(request, self.order)
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
        return ctx

    @cached_property
    def form(self):
        return self.payment_provider.payment_form_render(self.request)

    def get_confirm_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay.confirm', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderInvoiceCreate(EventViewMixin, OrderDetailMixin, View):

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.request.event.settings.get('invoice_generate') != 'user' or not invoice_qualified(self.order):
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


class OrderPayDo(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_pay_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        can_do = self.payment_provider.order_can_retry(self.order) or 'payment_change_{}'.format(self.order.pk) in request.session
        if not can_do or not self.payment_provider.is_enabled:
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())
        if (not self.payment_provider.payment_is_valid_session(request)
                or not self.payment_provider.is_enabled):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = self.payment_provider.payment_perform(request, self.order)
        if 'payment_change_{}'.format(self.order.pk) in request.session:
            del request.session['payment_change_{}'.format(self.order.pk)]
        return redirect(resp or self.get_order_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
        ctx['payment_provider'] = self.payment_provider
        return ctx

    def get_payment_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderPayComplete(EventViewMixin, OrderDetailMixin, View):
    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if (not self.payment_provider.payment_is_valid_session(request) or
                not self.payment_provider.is_enabled):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        resp = self.payment_provider.payment_perform(request, self.order)
        return redirect(resp or self.get_order_url() + '?paid=yes')

    def get_payment_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderPayChangeMethod(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = 'pretixpresale/event/order_pay_change.html'

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            messages.error(request, _('The payment method for this order cannot be changed.'))
            return redirect(self.get_order_url() + '?paid=yes')
        return super().dispatch(request, *args, **kwargs)

    def get_payment_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })

    @cached_property
    def _total_order_value(self):
        return self.order.positions.aggregate(sum=Sum('price'))['sum']

    @cached_property
    def provider_forms(self):
        providers = []
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                continue
            if not provider.is_enabled or not provider.order_change_allowed(self.order):
                continue
            fee = provider.calculate_fee(self._total_order_value)
            providers.append({
                'provider': provider,
                'fee': fee,
                'fee_diff': fee - self.order.payment_fee,
                'fee_diff_abs': abs(fee - self.order.payment_fee),
                'form': provider.payment_form_render(self.request)
            })
        return providers

    def post(self, request, *args, **kwargs):
        self.request = request
        for p in self.provider_forms:
            if p['provider'].identifier == request.POST.get('payment', ''):
                request.session['payment'] = p['provider'].identifier
                request.session['payment_change_{}'.format(self.order.pk)] = '1'

                resp = p['provider'].order_prepare(request, self.order)
                if resp:
                    with transaction.atomic():
                        new_fee = p['provider'].calculate_fee(self._total_order_value)
                        self.order.log_action('pretix.event.order.payment.changed', {
                            'old_fee': self.order.payment_fee,
                            'new_fee': new_fee,
                            'old_provider': self.order.payment_provider,
                            'new_provider': p['provider'].identifier
                        })
                        self.order.payment_provider = p['provider'].identifier
                        self.order.payment_fee = new_fee
                        self.order._calculate_tax()
                        self.order.save()

                        i = self.order.invoices.filter(is_cancellation=False).last()
                        if i:
                            generate_cancellation(i)
                            generate_invoice(self.order)
                if isinstance(resp, str):
                    return redirect(resp)
                elif resp is True:
                    return redirect(self.get_confirm_url())
                else:
                    return self.get(request, *args, **kwargs)
        messages.error(self.request, _("Please select a payment method."))
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['providers'] = self.provider_forms
        return ctx

    def get_confirm_url(self):
        return eventreverse(self.request.event, 'presale:event.order.pay.confirm', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        })


class OrderModify(EventViewMixin, OrderDetailMixin, QuestionsViewMixin, TemplateView):
    template_name = "pretixpresale/event/order_modify.html"

    @cached_property
    def positions(self):
        return list(self.order.positions.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation', 'item__questions', 'answers'
        ))

    @cached_property
    def invoice_address(self):
        try:
            return self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            return InvoiceAddress(order=self.order)

    @cached_property
    def invoice_form(self):
        return InvoiceAddressForm(data=self.request.POST if self.request.method == "POST" else None,
                                  event=self.request.event,
                                  instance=self.invoice_address)

    def post(self, request, *args, **kwargs):
        failed = not self.save() or not self.invoice_form.is_valid()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(request, *args, **kwargs)
        self.invoice_form.save()
        self.order.log_action('pretix.event.order.modified')
        if self.invoice_form.has_changed():
            success_message = ('Your invoice address has been updated. Please contact us if you need us '
                               'to regenerate your invoice.')
            messages.success(self.request, _(success_message))
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['forms'] = self.forms
        ctx['invoice_form'] = self.invoice_form
        return ctx


class OrderCancel(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_cancel.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.order.status != Order.STATUS_PENDING or not self.order.can_user_cancel:
            messages.error(request, _('You cannot cancel this order.'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


class OrderCancelDo(EventViewMixin, OrderDetailMixin, AsyncAction, View):
    task = cancel_order

    def get_success_url(self, value):
        return self.get_order_url()

    def get_error_url(self):
        return self.get_order_url()

    def post(self, request, *args, **kwargs):
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if not self.order.can_user_cancel:
            messages.error(request, _('You cannot cancel this order.'))
            return redirect(self.get_order_url())
        return self.do(self.order.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx

    def get_success_message(self, value):
        return _('The order has been cancelled.')

    def get_error_message(self, exception):
        if isinstance(exception, dict) and exception['exc_type'] == 'OrderError':
            return gettext(exception['exc_message'])
        elif isinstance(exception, OrderError):
            return str(exception)
        return super().get_error_message(exception)


class OrderDownload(EventViewMixin, OrderDetailMixin, View):
    @cached_property
    def output(self):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.kwargs.get('output'):
                return provider

    def get(self, request, *args, **kwargs):
        if not self.output or not self.output.is_enabled:
            messages.error(request, _('You requested an invalid ticket output type.'))
            return redirect(self.get_order_url())
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        if self.order.status != Order.STATUS_PAID:
            messages.error(request, _('Order is not paid.'))
            return redirect(self.get_order_url())
        if (not self.request.event.settings.ticket_download
            or (self.request.event.settings.ticket_download_date is not None
                and now() < self.request.event.settings.ticket_download_date)):
            messages.error(request, _('Ticket download is not (yet) enabled.'))
            return redirect(self.get_order_url())

        try:
            ct = CachedTicket.objects.get(order=self.order, provider=self.output.identifier)
        except CachedTicket.DoesNotExist:
            ct = CachedTicket(order=self.order, provider=self.output.identifier)
        try:
            ct.cachedfile
        except CachedFile.DoesNotExist:
            cf = CachedFile()
            cf.date = now()
            cf.expires = self.request.event.date_from + timedelta(days=30)
            cf.save()
            ct.cachedfile = cf
        ct.save()
        generate(self.order.id, self.output.identifier)
        return redirect(reverse('cachedfile.download', kwargs={'id': ct.cachedfile.id}))


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

        if not invoice.file:
            # This happens if we have celery installed and the file will be generated in the background
            messages.warning(request, _('The invoice file has not yet been generated, we will generate it for you '
                                        'now. Please try again in a few seconds.'))
            return redirect(self.get_order_url())

        return redirect(invoice.file.url)
