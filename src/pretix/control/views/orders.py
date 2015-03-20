from django.views.generic import ListView

from pretix.base.models import Order


class OrderList(ListView):
    model = Order
    context_object_name = 'orders'
    template_name = 'pretixcontrol/orders/index.html'
    paginate_by = 30

    def get_queryset(self):
        return Order.objects.current.filter(
            event=self.request.event
        ).select_related("user")
