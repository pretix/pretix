from itertools import groupby
from django.db.models import Q
from django.views.generic import ListView, DetailView

from pretix.base.models import Order
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


class OrderDetail(EventPermissionRequiredMixin, DetailView):
    model = Order
    context_object_name = 'order'
    template_name = 'pretixcontrol/order/index.html'
    permission = 'can_view_orders'

    def get_object(self, queryset=None):
        return Order.objects.current.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.get_items()
        ctx['event'] = self.request.event
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
            if ((pos.item.admission and self.request.event.settings.attendee_names_asked == 'True')
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
