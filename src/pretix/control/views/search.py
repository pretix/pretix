from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import ListView

from pretix.base.models import Order
from pretix.control.forms.filter import OrderSearchFilterForm


class OrderSearch(ListView):
    model = Order
    context_object_name = 'orders'
    paginate_by = 30
    template_name = 'pretixcontrol/search/orders.html'

    @cached_property
    def filter_form(self):
        return OrderSearchFilterForm(data=self.request.GET, request=self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['filter_form'] = self.filter_form
        return ctx

    def get_queryset(self):
        qs = Order.objects.all()
        if not self.request.user.is_superuser:
            qs = qs.filter(
                Q(event__organizer_id__in=self.request.user.teams.filter(
                    all_events=True, can_view_orders=True).values_list('organizer', flat=True))
                | Q(event_id__in=self.request.user.teams.filter(
                    can_view_orders=True).values_list('limit_events__id', flat=True))
            )

        if self.filter_form.is_valid():
            fdata = self.filter_form.cleaned_data
            if fdata.get('query'):
                u = fdata.get('query')
                if "-" in u:
                    code = (Q(event__slug__icontains=u.split("-")[0])
                            & Q(code__icontains=Order.normalize_code(u.split("-")[1])))
                else:
                    code = Q(code__icontains=Order.normalize_code(u))
                qs = qs.filter(
                    code
                    | Q(email__icontains=u)
                    | Q(positions__attendee_name__icontains=u)
                    | Q(positions__attendee_email__icontains=u)
                    | Q(invoice_address__name__icontains=u)
                    | Q(invoice_address__company__icontains=u)
                )

            if fdata.get('status'):
                s = fdata.get('status')
                if s == 'o':
                    qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now().replace(hour=0, minute=0, second=0))
                elif s == 'ne':
                    qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
                else:
                    qs = qs.filter(status=s)

            if fdata.get('organizer'):
                qs = qs.filter(event__organizer=fdata.get('organizer'))

        if self.request.GET.get("ordering", "") != "":
            p = self.request.GET.get("ordering", "")
            p_admissable = ('event', '-event', '-code', 'code', '-email', 'email', '-total', 'total', '-datetime',
                            'datetime', '-status', 'status')
            if p in p_admissable:
                qs = qs.order_by(p)

        return qs.distinct().prefetch_related('event', 'event__organizer')
