from itertools import groupby
from django.db.models import Q
from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django.http import HttpResponseNotFound
from pretix.base.models import Order, OrderPosition
from pretix.base.signals import register_payment_providers
from pretix.presale.views import EventViewMixin, EventLoginRequiredMixin, CartDisplayMixin


class OrderDetails(EventViewMixin, EventLoginRequiredMixin, CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/order.html"

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

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound
        return super().get(request, *args, **kwargs)

    def itemlist_cartlike(self):
        """
        Returns the list of ordered items a format compatible to the
        CardDisplayMixin, so we can reuse template code
        """
        cartpos = OrderPosition.objects.current.filter(
            order=self.order,
        ).order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions'
        )

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if (pos.item.admission and self.request.event.settings.attendee_names_asked == 'True') \
                    or pos.item.questions.all():
                return pos.id, "", "", ""
            return "", pos.item_id, pos.variation_id, pos.price

        positions = []
        for k, g in groupby(sorted(list(cartpos), key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            positions.append(group)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.order.total,
            'payment_fee': self.order.payment_fee,
        }

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['cart'] = self.get_cart(
            answers=True,
            queryset=OrderPosition.objects.current.filter(order=self.order)
        )
        if self.order.status == Order.STATUS_PENDING:
            ctx['payment'] = self.payment_provider.order_pending_render(self.request, self.order)
        elif self.order.status == Order.STATUS_PAID:
            ctx['payment'] = self.payment_provider.order_paid_render(self.request, self.order)
        return ctx
