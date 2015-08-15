import datetime
import json
from decimal import Decimal

import dateutil.parser
import dateutil.rrule
from django.db.models import Count, Sum
from django.views.generic import TemplateView

from pretix.base.models import Item, Order, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin


class IndexView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/statistics/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Orders by day
        ordered_by_day = {
            # we receive different types depending on whether we are running on
            # MySQL or SQLite
            (
                o['datetime']
                if isinstance(o['datetime'], datetime.date)
                else dateutil.parser.parse(o['datetime']).date()
            ): o['count']
            for o in
            Order.objects.current.filter(event=self.request.event).extra({'datetime': "date(datetime)"}).values(
                'datetime').annotate(count=Count('id'))
        }
        paid_by_day = {
            o['payment_date'].date(): o['count']
            for o in
            Order.objects.current.filter(event=self.request.event, payment_date__isnull=False).values(
                'payment_date').annotate(count=Count('id'))
        }
        data = []
        for d in dateutil.rrule.rrule(
                dateutil.rrule.DAILY,
                dtstart=min(ordered_by_day.keys()),
                until=max(max(ordered_by_day.keys()), max(paid_by_day.keys()))):
            d = d.date()
            data.append({
                'date': d.strftime('%Y-%m-%d'),
                'ordered': ordered_by_day.get(d, 0),
                'paid': paid_by_day.get(d, 0)
            })

        ctx['obd_data'] = json.dumps(data)

        # Orders by product
        num_ordered = {
            p['item']: p['cnt']
            for p in (OrderPosition.objects.current
                      .filter(order__event=self.request.event)
                      .values('item', 'variation')
                      .annotate(cnt=Count('id')))
        }
        num_paid = {
            p['item']: p['cnt']
            for p in (OrderPosition.objects.current
                      .filter(order__event=self.request.event, order__status=Order.STATUS_PAID)
                      .values('item', 'variation')
                      .annotate(cnt=Count('id')))
        }
        item_names = {
            i.identity: str(i.name)
            for i in Item.objects.current.filter(event=self.request.event)
        }
        ctx['obp_data'] = [
            {
                'item': item_names[item],
                'ordered': cnt,
                'paid': num_paid.get(item, 0)
            } for item, cnt in num_ordered.items()
        ]

        rev_by_day = {
            o['payment_date'].date(): o['sum']
            for o in
            Order.objects.current.filter(event=self.request.event,
                                         status=Order.STATUS_PAID,
                                         payment_date__isnull=False).values(
                'payment_date').annotate(sum=Sum('total'))
        }
        data = []
        total = 0
        for d in dateutil.rrule.rrule(
                dateutil.rrule.DAILY,
                dtstart=min(rev_by_day.keys()),
                until=max(rev_by_day.keys())):
            d = d.date()
            total += float(rev_by_day.get(d, 0))
            data.append({
                'date': d.strftime('%Y-%m-%d'),
                'revenue': round(total, 2),
            })
        ctx['rev_data'] = json.dumps(data)

        return ctx
