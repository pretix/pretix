from itertools import groupby
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.views.generic import ListView, DetailView
from pretix.base.forms import VersionedModelForm

from pretix.base.models import Order, Quota
from pretix.base.signals import register_payment_providers
from pretix.control.permissions import EventPermissionRequiredMixin


class OrderList(EventPermissionRequiredMixin, ListView):
    model = Order
    context_object_name = 'orders'
    template_name = 'pretixcontrol/orders/index.html'
    paginate_by = 30
    permission = 'can_view_orders'

    def get_queryset(self):
        return Order.objects.current.filter(
            event=self.request.event
        ).select_related("user")


class OrderView(EventPermissionRequiredMixin, DetailView):
    context_object_name = 'order'
    model = Order

    def get_object(self, queryset=None):
        return Order.objects.current.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )

    @cached_property
    def order(self):
        return self.get_object()

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider


class ExtendForm(VersionedModelForm):
    class Meta:
        model = Order
        fields = ['expires']


class OrderDetail(OrderView):
    template_name = 'pretixcontrol/order/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.get_items()
        ctx['event'] = self.request.event
        ctx['payment'] = self.payment_provider.order_control_render(self.request, self.object)
        return ctx

    def get_items(self):
        queryset = self.object.positions.all()

        cartpos = queryset.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop', 'item__questions',
            'answers'
        )

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if ((pos.item.admission and self.request.event.settings.attendee_names_asked)
                    or pos.item.questions.all()):
                return pos.id, "", "", ""
            return "", pos.item_id, pos.variation_id, pos.price

        positions = []
        for k, g in groupby(sorted(list(cartpos), key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.has_questions = k[0] != ""
            group.cache_answers()
            positions.append(group)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.object.total,
            'payment_fee': self.object.payment_fee,
        }


class OrderTransition(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        to = self.request.POST.get('status', '')
        if self.order.status == 'n' and to == 'p':
            try:
                self.order.mark_paid(manual=True)
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
            else:
                messages.success(self.request, _('The order has been marked as paid.'))
        elif self.order.status == 'n' and to == 'c':
            order = self.order.clone()
            order.status = Order.STATUS_CANCELLED
            order.save()
            messages.success(self.request, _('The order has been cancelled.'))
        elif self.order.status == 'p' and to == 'n':
            order = self.order.clone()
            order.status = Order.STATUS_PENDING
            order.payment_manual = True
            order.save()
            messages.success(self.request, _('The order has been marked as not paid.'))
        elif self.order.status == 'p' and to == 'r':
            ret = self.payment_provider.order_control_refund_perform(self.request, self.order)
            if ret:
                return redirect(ret)
        return redirect(reverse(
            'control:event.order',
            kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug,
                'code': self.order.code,
            }
        ))

    def get(self, *args, **kwargs):
        to = self.request.GET.get('status', '')
        if self.order.status == 'n' and to == 'c':
            return render(self.request, 'pretixcontrol/order/cancel.html', {
                'order': self.order,
            })
        elif self.order.status == 'p' and to == 'r':
            return render(self.request, 'pretixcontrol/order/refund.html', {
                'order': self.order,
                'payment': self.payment_provider.order_control_refund_render(self.order),
            })
        else:
            return HttpResponse(status=405)


class OrderExtend(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.order.status != Order.STATUS_PENDING:
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        oldvalue = self.order.expires

        if self.form.is_valid():
            if oldvalue > now():
                self.form.save()
            else:
                is_available, _quotas_locked = self.order._is_still_available(keep_locked=False)
                if is_available is True:
                    self.form.save()
                    messages.success(self.request, _('The payment term has been changed.'))
                else:
                    messages.error(self.request, is_available)
            return self._redirect_back()
        else:
            return self.get(*args, **kwargs)

    def _redirect_back(self):
        return redirect(reverse(
            'control:event.order',
            kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug,
                'code': self.order.code,
            }
        ))

    def get(self, *args, **kwargs):
        if self.order.status != Order.STATUS_PENDING:
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        return render(self.request, 'pretixcontrol/order/extend.html', {
            'order': self.order,
            'form': self.form,
        })

    @cached_property
    def form(self):
        return ExtendForm(instance=self.order,
                          data=self.request.POST if self.request.method == "POST" else None)
