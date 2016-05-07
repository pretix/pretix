from django.views.generic import ListView

from pretix.base.models import Item, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin


class AttendeeList(EventPermissionRequiredMixin, ListView):
    model = OrderPosition
    context_object_name = 'attendees'
    template_name = 'pretixcontrol/attendees/index.html'
    paginate_by = 30
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = OrderPosition.objects.filter(
            order__event=self.request.event,
            item__admission=True
        ).select_related('order')
        if self.request.GET.get("status", "") != "":
            s = self.request.GET.get("status", "")
            qs = qs.filter(order__status=s)
        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(item_id__in=(i,)).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event, admission=True)
        ctx['filtered'] = ("status" in self.request.GET or "item" in self.request.GET)
        return ctx
