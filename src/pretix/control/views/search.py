from django.db.models import Q
from django.utils.functional import cached_property
from django.views.generic import ListView

from pretix.base.models import Order
from pretix.control.forms.filter import OrderSearchFilterForm
from pretix.control.views import LargeResultSetPaginator, PaginationMixin


class OrderSearch(PaginationMixin, ListView):
    model = Order
    paginator_class = LargeResultSetPaginator
    context_object_name = 'orders'
    template_name = 'pretixcontrol/search/orders.html'

    @cached_property
    def filter_form(self):
        return OrderSearchFilterForm(data=self.request.GET, request=self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['filter_form'] = self.filter_form
        return ctx

    def get_queryset(self):
        qs = Order.objects.select_related('invoice_address')
        if not self.request.user.has_active_staff_session(self.request.session.session_key):
            qs = qs.filter(
                Q(event__organizer_id__in=self.request.user.teams.filter(
                    all_events=True, can_view_orders=True).values_list('organizer', flat=True))
                | Q(event_id__in=self.request.user.teams.filter(
                    can_view_orders=True).values_list('limit_events__id', flat=True))
            )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs.only(
            'id', 'invoice_address__name_cached', 'invoice_address__name_parts', 'code', 'event', 'email',
            'datetime', 'total', 'status'
        ).prefetch_related(
            'event', 'event__organizer'
        )
