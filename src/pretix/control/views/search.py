#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.conf import settings
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.utils.functional import cached_property
from django.views.generic import ListView

from pretix.base.models import Order, OrderPosition
from pretix.base.models.orders import CancellationRequest, OrderPayment
from pretix.control.forms.filter import (
    OrderPaymentSearchFilterForm, OrderSearchFilterForm,
)
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
        ctx['meta_fields'] = [
            self.filter_form[k] for k in self.filter_form.fields if k.startswith('meta_')
        ]

        # Only compute these annotations for this page (query optimization)
        s = OrderPosition.objects.filter(
            order=OuterRef('pk')
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        annotated = {
            o['pk']: o
            for o in
            Order.annotate_overpayments(Order.objects).using(settings.DATABASE_REPLICA).filter(
                pk__in=[o.pk for o in ctx['orders']]
            ).annotate(
                pcnt=Subquery(s, output_field=IntegerField()),
                has_cancellation_request=Exists(CancellationRequest.objects.filter(order=OuterRef('pk')))
            ).values(
                'pk', 'pcnt', 'is_overpaid', 'is_underpaid', 'is_pending_with_full_payment', 'has_external_refund',
                'has_pending_refund', 'has_cancellation_request'
            )
        }

        for o in ctx['orders']:
            if o.pk not in annotated:
                continue
            o.pcnt = annotated.get(o.pk)['pcnt']
            o.is_overpaid = annotated.get(o.pk)['is_overpaid']
            o.is_underpaid = annotated.get(o.pk)['is_underpaid']
            o.is_pending_with_full_payment = annotated.get(o.pk)['is_pending_with_full_payment']
            o.has_external_refund = annotated.get(o.pk)['has_external_refund']
            o.has_pending_refund = annotated.get(o.pk)['has_pending_refund']
            o.has_cancellation_request = annotated.get(o.pk)['has_cancellation_request']

        return ctx

    def get_queryset(self):
        qs = Order.objects.using(settings.DATABASE_REPLICA)

        if not self.request.user.has_active_staff_session(self.request.session.session_key):
            qs = qs.filter(
                Q(event_id__in=self.request.user.get_events_with_permission('can_view_orders').values_list('id', flat=True))
            )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

            if self.filter_form.use_query_hack():
                """
                We need to work around a bug in PostgreSQL's query plan optimizer here.
                The database lacks statistical data to predict how common our search filter is and therefore
                assumes that it is cheaper to first ORDER *all* orders in the system (since we got an index on
                datetime), then filter out with a full scan until OFFSET/LIMIT condition is fulfilled. If we
                look for something rare (such as an email address used once within hundreds of thousands of
                orders, this ends up to be pathologically slow.

                Generally, PostgreSQL tries to make these decisions on statistical data and generally, they *can*
                only be made on statistical data, so it's a little bit of a stretch that we try to do it better
                than PostgreSQL here. However, experience suggests applying this tricks works specifically in the
                cases where the WHERE part of the statement is very hard to compute, e.g. uses a complicated
                condition that can't utilize indices well.

                For some search queries on pretix.eu, we see search times of >30s, just due to the ORDER BY and
                LIMIT clause. Without them. the query runs in roughly 0.6s. This heuristic approach tries to
                detect these cases and rewrite the query as a nested subquery that strongly suggests sorting
                before filtering. However, since even that fails in some cases because PostgreSQL thinks it knows
                better, we literally force it by evaluating the subquery explicitly. We only do this for n<=200,
                to avoid memory leaks – and problems with maximum parameter count on SQLite. In cases where the
                search query yields lots of results, this will actually be slower since it requires two queries,
                sorry.

                Phew.
                """
                resultids = list(qs.order_by().values_list('id', flat=True)[:201])
                if len(resultids) <= 200:
                    qs = Order.objects.using(settings.DATABASE_REPLICA).filter(
                        id__in=resultids
                    )

        """
        We use prefetch_related here instead of select_related for a reason, even though select_related
        would be the common choice for a foreign key and doesn't require an additional database query.
        The problem is, that if our results contain the same event 25 times, select_related will create
        25 Django  objects which will all try to pull their ownsettings cache to show the event properly,
        leading to lots of unnecessary queries. Due to the way prefetch_related works differently, it
        will only create one shared Django object.
        """
        return qs.only(
            'id', 'invoice_address__name_cached', 'invoice_address__name_parts', 'code', 'event', 'email',
            'datetime', 'total', 'status', 'require_approval', 'testmode', 'custom_followup_at', 'expires'
        ).prefetch_related(
            'event', 'event__organizer'
        ).select_related('invoice_address')


class PaymentSearch(PaginationMixin, ListView):
    model = OrderPayment
    paginator_class = LargeResultSetPaginator
    context_object_name = 'payments'
    template_name = 'pretixcontrol/search/payments.html'

    @cached_property
    def filter_form(self):
        return OrderPaymentSearchFilterForm(data=self.request.GET, request=self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['filter_form'] = self.filter_form
        return ctx

    def get_queryset(self):
        qs = OrderPayment.objects.using(settings.DATABASE_REPLICA)

        if not self.request.user.has_active_staff_session(self.request.session.session_key):
            qs = qs.filter(
                Q(order__event_id__in=self.request.user.get_events_with_permission('can_view_orders').values_list('id', flat=True))
            )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

            if self.filter_form.cleaned_data.get('query'):
                """
                We need to work around a bug in PostgreSQL's query plan optimizer here.
                The database lacks statistical data to predict how common our search filter is and therefore
                assumes that it is cheaper to first ORDER *all* orders in the system (since we got an index on
                datetime), then filter out with a full scan until OFFSET/LIMIT condition is fulfilled. If we
                look for something rare (such as an email address used once within hundreds of thousands of
                orders, this ends up to be pathologically slow.

                For some search queries on pretix.eu, we see search times of >30s, just due to the ORDER BY and
                LIMIT clause. Without them. the query runs in roughly 0.6s. This heuristical approach tries to
                detect these cases and rewrite the query as a nested subquery that strongly suggests sorting
                before filtering. However, since even that fails in some cases because PostgreSQL thinks it knows
                better, we literally force it by evaluating the subquery explicitly. We only do this for n<=200,
                to avoid memory leaks – and problems with maximum parameter count on SQLite. In cases where the
                search query yields lots of results, this will actually be slower since it requires two queries,
                sorry.

                Phew.
                """

                page = self.kwargs.get(self.page_kwarg) or self.request.GET.get(self.page_kwarg) or 1
                limit = self.get_paginate_by(None)
                try:
                    offset = (int(page) - 1) * limit
                except ValueError:
                    offset = 0
                resultids = list(qs.order_by().values_list('id', flat=True)[:201])
                if len(resultids) <= 200 and len(resultids) <= offset + limit:
                    qs = OrderPayment.objects.using(settings.DATABASE_REPLICA).filter(
                        id__in=resultids
                    )

        """
        We use prefetch_related here instead of select_related for a reason, even though select_related
        would be the common choice for a foreign key and doesn't require an additional database query.
        The problem is, that if our results contain the same event 25 times, select_related will create
        25 Django  objects which will all try to pull their ownsettings cache to show the event properly,
        leading to lots of unnecessary queries. Due to the way prefetch_related works differently, it
        will only create one shared Django object.
        """
        return qs.prefetch_related('order', 'order__event', 'order__event__organizer')
