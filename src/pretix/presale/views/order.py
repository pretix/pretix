from datetime import timedelta

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView, View

from pretix.base.models import CachedFile, CachedTicket, Order, OrderPosition
from pretix.base.services.tickets import generate
from pretix.base.signals import (
    register_payment_providers, register_ticket_outputs,
)
from pretix.presale.views import CartDisplayMixin, EventViewMixin
from pretix.presale.views.checkout import QuestionsViewMixin


class OrderDetailMixin:
    @cached_property
    def order(self):
        try:
            q = Q(Q(secret__isnull=False) & Q(secret__in=self.request.session['order_secrets']))
            if self.request.user.is_authenticated():
                q |= Q(user=self.request.user)
            return Order.objects.current.get(q & Q(event=self.request.event) & Q(code=self.kwargs['order']))
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
        return reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
        })


class OrderDetails(EventViewMixin, OrderDetailMixin, CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/order.html"

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or order does belong to another user.'))
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
            queryset=OrderPosition.objects.current.filter(order=self.order)
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
            raise Http404(_('Unknown order code or order does belong to another user.'))
        if (self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED)
                or not self.payment_provider.order_can_retry(self.order)
                or not self.payment_provider.is_enabled):
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = self.payment_provider.retry_prepare(
            request, self.order
        )
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
        return reverse('presale:event.order.pay.confirm', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
        })


class OrderPayDo(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_pay_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.order:
            raise Http404(_('Unknown order code or order does belong to another user.'))
        if not self.payment_provider.order_can_retry(self.order) or not self.payment_provider.is_enabled:
            messages.error(request, _('The payment for this order cannot be continued.'))
            return redirect(self.get_order_url())
        if (not self.payment_provider.payment_is_valid_session(request)
                or not self.payment_provider.is_enabled
                or not self.payment_provider.is_allowed(request)):
            messages.error(request, _('The payment information you entered was incomplete.'))
            return redirect(self.get_payment_url())
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = self.payment_provider.payment_perform(request, self.order)
        return redirect(resp or self.get_order_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['payment'] = self.payment_provider.checkout_confirm_render(self.request)
        ctx['payment_provider'] = self.payment_provider
        return ctx

    @cached_property
    def form(self):
        return self.payment_provider.payment_form_render(self.request)

    def get_payment_url(self):
        return reverse('presale:event.order.pay', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
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
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))

    def post(self, request, *args, **kwargs):
        failed = not self.save()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(request, *args, **kwargs)
        return redirect(self.get_order_url())

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            raise Http404(request, _('Unknown order code or order does belong to another user.'))
        if not self.order.can_modify_answers:
            messages.error(request, _('You cannot modify this order'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['forms'] = self.forms
        return ctx


class OrderCancel(EventViewMixin, OrderDetailMixin, TemplateView):
    template_name = "pretixpresale/event/order_cancel.html"

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            raise Http404(_('Unknown order code or order does belong to another user.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            messages.error(request, _('You cannot cancel this order'))
            return redirect(self.get_order_url())
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        order = self.order.clone()
        order.status = Order.STATUS_CANCELLED
        order.save()
        return redirect(self.get_order_url())

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


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
            raise Http404(_('Unknown order code or order does belong to another user.'))
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
        generate(self.order.identity, self.output.identifier)
        return redirect(reverse('cachedfile.download', kwargs={'id': ct.cachedfile.id}))
