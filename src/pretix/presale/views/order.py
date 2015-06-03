from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View
from django.http import HttpResponseNotFound, HttpResponseForbidden
from pretix.base.models import Order, OrderPosition
from pretix.base.signals import register_payment_providers, register_ticket_outputs
from pretix.presale.views import EventViewMixin, EventLoginRequiredMixin, CartDisplayMixin
from pretix.presale.views.checkout import QuestionsViewMixin


class OrderDetailMixin:
    @cached_property
    def order(self):
        try:
            return Order.objects.current.get(
                user=self.request.user,
                event=self.request.event,
                code=self.kwargs['order'],
            )
        except Order.DoesNotExist:
            return None


class OrderDetails(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                   CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/order.html"

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        return super().get(request, *args, **kwargs)

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider

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
            and now() > self.request.event.settings.ticket_download_date
            and self.order.status == Order.STATUS_PAID
        )
        ctx['download_buttons'] = self.download_buttons
        ctx['cart'] = self.get_cart(
            answers=True,
            queryset=OrderPosition.objects.current.filter(order=self.order)
        )
        if self.order.status == Order.STATUS_PENDING:
            ctx['payment'] = self.payment_provider.order_pending_render(self.request, self.order)
        elif self.order.status == Order.STATUS_PAID:
            ctx['payment'] = self.payment_provider.order_paid_render(self.request, self.order)
        return ctx


class OrderModify(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                  QuestionsViewMixin, TemplateView):
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
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if not self.order.can_modify_answers:
            return HttpResponseForbidden(_('You cannot modify this order'))
        failed = not self.save()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(*args, **kwargs)
        return redirect('presale:event.order',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        order=self.order.code)

    def get(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if not self.order.can_modify_answers:
            return HttpResponseForbidden(_('You cannot modify this order'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['forms'] = self.forms
        return ctx


class OrderCancel(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                  TemplateView):
    template_name = "pretixpresale/event/order_cancel.html"

    def post(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            return HttpResponseForbidden(_('You cannot cancel this order'))
        order = self.order.clone()
        order.status = Order.STATUS_CANCELLED
        order.save()
        return redirect('presale:event.order',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        order=order.code)

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            return HttpResponseForbidden(_('You cannot cancel this order'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


class OrderDownload(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                    View):
    def get_order_url(self):
        return reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
        })

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
        if self.order.status != Order.STATUS_PAID:
            messages.error(request, _('Order is not paid.'))
            return redirect(self.get_order_url())
        if not self.request.event.settings.ticket_download or now() < self.request.event.settings.ticket_download_date:
            messages.error(request, _('Ticket download is not (yet) enabled.'))
            return redirect(self.get_order_url())
        return self.output.generate(request, self.order)
