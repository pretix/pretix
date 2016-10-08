import datetime
import json

import dateutil.parser
import dateutil.rrule
from django.db.models import Count
from django.utils import timezone
from django.views.generic import TemplateView

from pretix.base.models import Item, Order, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import ChartContainingView
from pretix.plugins.statistics.signals import clear_cache


class IndexView(EventPermissionRequiredMixin, ChartContainingView, TemplateView):
    template_name = 'pretixplugins/statistics/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tz = timezone.get_current_timezone()

        if 'latest' in self.request.GET:
            clear_cache(self.request.event)

        cache = self.request.event.get_cache()

        # Orders by day
        ctx['obd_data'] = cache.get('statistics_obd_data')
        if not ctx['obd_data']:
            ordered_by_day = {}
            for o in Order.objects.filter(event=self.request.event).values('datetime'):
                day = o['datetime'].astimezone(tz).date()
                ordered_by_day[day] = ordered_by_day.get(day, 0) + 1
            paid_by_day = {}
            for o in Order.objects.filter(event=self.request.event,
                                          payment_date__isnull=False).values('payment_date'):
                day = o['payment_date'].astimezone(tz).date()
                paid_by_day[day] = paid_by_day.get(day, 0) + 1

            data = []
            for d in dateutil.rrule.rrule(
                    dateutil.rrule.DAILY,
                    dtstart=min(ordered_by_day.keys()) if ordered_by_day else datetime.date.today(),
                    until=max(
                        max(ordered_by_day.keys() if paid_by_day else [datetime.date.today()]),
                        max(paid_by_day.keys() if paid_by_day else [datetime.date(1970, 1, 1)])
                    )):
                d = d.date()
                data.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'ordered': ordered_by_day.get(d, 0),
                    'paid': paid_by_day.get(d, 0)
                })

            ctx['obd_data'] = json.dumps(data)
            cache.set('statistics_obd_data', ctx['obd_data'])

        # Orders by product
        ctx['obp_data'] = cache.get('statistics_obp_data')
        if not ctx['obp_data']:
            num_ordered = {
                p['item']: p['cnt']
                for p in (OrderPosition.objects
                          .filter(order__event=self.request.event)
                          .values('item')
                          .annotate(cnt=Count('id')))
            }
            num_paid = {
                p['item']: p['cnt']
                for p in (OrderPosition.objects
                          .filter(order__event=self.request.event, order__status=Order.STATUS_PAID)
                          .values('item')
                          .annotate(cnt=Count('id')))
            }
            item_names = {
                i.id: str(i.name)
                for i in Item.objects.filter(event=self.request.event)
            }
            ctx['obp_data'] = json.dumps([
                {
                    'item': item_names[item],
                    'ordered': cnt,
                    'paid': num_paid.get(item, 0)
                } for item, cnt in num_ordered.items()
            ])
            cache.set('statistics_obp_data', ctx['obp_data'])

        ctx['rev_data'] = cache.get('statistics_rev_data')
        if not ctx['rev_data']:
            rev_by_day = {}
            for o in Order.objects.filter(event=self.request.event,
                                          status=Order.STATUS_PAID,
                                          payment_date__isnull=False).values('payment_date', 'total'):
                day = o['payment_date'].astimezone(tz).date()
                rev_by_day[day] = rev_by_day.get(day, 0) + o['total']

            data = []
            total = 0
            for d in dateutil.rrule.rrule(
                    dateutil.rrule.DAILY,
                    dtstart=min(rev_by_day.keys() if rev_by_day else [datetime.date.today()]),
                    until=max(rev_by_day.keys() if rev_by_day else [datetime.date.today()])):
                d = d.date()
                total += float(rev_by_day.get(d, 0))
                data.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'revenue': round(total, 2),
                })
            ctx['rev_data'] = json.dumps(data)
            cache.set('statistics_rev_data', ctx['rev_data'])

        ctx['has_orders'] = self.request.event.orders.exists()

        return ctx
