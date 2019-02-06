from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.utils.functional import cached_property
from django.views.generic import ListView

from pretix.base.models import Order, OrderPosition
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

        # Only compute this annotations for this page (query optimization)
        s = OrderPosition.objects.filter(
            order=OuterRef('pk')
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        annotated = {
            o['pk']: o
            for o in
            Order.objects.filter(
                pk__in=[o.pk for o in ctx['orders']]
            ).annotate(
                pcnt=Subquery(s, output_field=IntegerField())
            ).values(
                'pk', 'pcnt',
            )
        }

        for o in ctx['orders']:
            if o.pk not in annotated:
                continue
            o.pcnt = annotated.get(o.pk)['pcnt']

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
            'datetime', 'total', 'status', 'require_approval'
        ).prefetch_related(
            'event', 'event__organizer'
        )
