from django.db.models import Prefetch, Q
from django.views.generic import ListView

from pretix.base.models import Checkin, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin


class CheckInView(EventPermissionRequiredMixin, ListView):
    model = Checkin
    context_object_name = 'entries'
    paginate_by = 30
    template_name = 'pretixcontrol/checkin/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):

        qs = OrderPosition.objects.filter(order__event=self.request.event, order__status='p')

        if self.request.GET.get("status", "") != "":
            p = self.request.GET.get("status", "")
            if p == '1':
                # records with check-in record
                qs = qs.filter(checkins__isnull=False)
            elif p == '0':
                qs = qs.filter(checkins__isnull=True)

        if self.request.GET.get("user", "") != "":
            u = self.request.GET.get("user", "")
            qs = qs.filter(
                Q(order__email__icontains=u) | Q(order__positions__attendee_name__icontains=u)
                | Q(order__positions__attendee_email__icontains=u)
            )

        if self.request.GET.get("item", "") != "":
            u = self.request.GET.get("item", "")
            qs = qs.filter(item__name__icontains=u)

        qs = qs.prefetch_related(
            Prefetch('checkins', queryset=Checkin.objects.filter(position__order__event=self.request.event))
        ).select_related('order', 'item')

        if self.request.GET.get("ordering", "") != "":
            p = self.request.GET.get("ordering", "")
            allowed_ordering_keys = ('-order__code', 'order__code', '-order__email', 'order__email',
                                     '-checkins__id', 'checkins__id', '-checkins__datetime', 'checkins__datetime',
                                     '-attendee_name', 'attendee_name', '-item__name', 'item__name')
            if p in allowed_ordering_keys:
                qs = qs.order_by(p)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtered'] = ("status" in self.request.GET or "user" in self.request.GET)
        return ctx
