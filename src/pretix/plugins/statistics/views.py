import datetime
import json
from decimal import Decimal

import dateutil.parser
import dateutil.rrule
from django.db.models import Count, DateTimeField, Max, Min, OuterRef, Subquery
from django.utils import timezone
from django.views.generic import TemplateView

from pretix.base.models import (
    Item, Order, OrderPayment, OrderPosition, SubEvent,
)
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

        subevent = None
        if self.request.GET.get("subevent", "") != "" and self.request.event.has_subevents:
            i = self.request.GET.get("subevent", "")
            try:
                subevent = self.request.event.subevents.get(pk=i)
            except SubEvent.DoesNotExist:
                pass

        cache = self.request.event.cache
        ckey = str(subevent.pk) if subevent else 'all'

        p_date = OrderPayment.objects.filter(
            order=OuterRef('pk'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()
        op_date = OrderPayment.objects.filter(
            order=OuterRef('order'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()

        # Orders by day
        ctx['obd_data'] = cache.get('statistics_obd_data' + ckey)
        if not ctx['obd_data']:
            oqs = Order.objects.annotate(payment_date=Subquery(p_date, output_field=DateTimeField()))
            if subevent:
                oqs = oqs.filter(all_positions__subevent_id=subevent, all_positions__canceled=False).distinct()

            ordered_by_day = {}
            for o in oqs.filter(event=self.request.event).values('datetime'):
                day = o['datetime'].astimezone(tz).date()
                ordered_by_day[day] = ordered_by_day.get(day, 0) + 1
            paid_by_day = {}
            for o in oqs.filter(event=self.request.event, payment_date__isnull=False).values('payment_date'):
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
            cache.set('statistics_obd_data' + ckey, ctx['obd_data'])

        # Orders by product
        ctx['obp_data'] = cache.get('statistics_obp_data' + ckey)
        if not ctx['obp_data']:
            opqs = OrderPosition.objects
            if subevent:
                opqs = opqs.filter(subevent=subevent)
            num_ordered = {
                p['item']: p['cnt']
                for p in (opqs
                          .filter(order__event=self.request.event)
                          .values('item')
                          .annotate(cnt=Count('id')).order_by())
            }
            num_paid = {
                p['item']: p['cnt']
                for p in (opqs
                          .filter(order__event=self.request.event, order__status=Order.STATUS_PAID)
                          .values('item')
                          .annotate(cnt=Count('id')).order_by())
            }
            item_names = {
                i.id: str(i)
                for i in Item.objects.filter(event=self.request.event)
            }
            ctx['obp_data'] = json.dumps([
                {
                    'item': item_names[item],
                    'item_short': item_names[item] if len(item_names[item]) < 15 else (item_names[item][:15] + "…"),
                    'ordered': cnt,
                    'paid': num_paid.get(item, 0)
                } for item, cnt in num_ordered.items()
            ])
            cache.set('statistics_obp_data' + ckey, ctx['obp_data'])

        ctx['rev_data'] = cache.get('statistics_rev_data' + ckey)
        if not ctx['rev_data']:
            rev_by_day = {}
            if subevent:
                for o in OrderPosition.objects.annotate(
                        payment_date=Subquery(op_date, output_field=DateTimeField())
                ).filter(order__event=self.request.event,
                         subevent=subevent,
                         order__status=Order.STATUS_PAID,
                         payment_date__isnull=False).values('payment_date', 'price'):
                    day = o['payment_date'].astimezone(tz).date()
                    rev_by_day[day] = rev_by_day.get(day, 0) + o['price']
            else:
                for o in Order.objects.annotate(
                        payment_date=Subquery(p_date, output_field=DateTimeField())
                ).filter(event=self.request.event,
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
            cache.set('statistics_rev_data' + ckey, ctx['rev_data'])

        ctx['has_orders'] = self.request.event.orders.exists()

        ctx['seats'] = {}

        if not self.request.event.has_subevents or (ckey != "all" and subevent):
            ev = subevent or self.request.event
            if ev.seating_plan_id is not None:
                seats_qs = ev.free_seats(sales_channel=None, include_blocked=True)
                ctx['seats']['blocked_seats'] = seats_qs.filter(blocked=True).count()
                ctx['seats']['free_seats'] = seats_qs.filter(blocked=False).count()
                ctx['seats']['purchased_seats'] = \
                    ev.seats.count() - ctx['seats']['blocked_seats'] - ctx['seats']['free_seats']

                seats_qs = seats_qs.values('product', 'blocked').annotate(count=Count('id'))\
                    .order_by('product__category__position', 'product__position', 'product', 'blocked')

                ctx['seats']['products'] = {}
                ctx['seats']['stats'] = {}
                item_cache = {i.pk: i for i in
                              self.request.event.items.annotate(has_variations=Count('variations')).filter(
                                  pk__in={p['product'] for p in seats_qs if p['product']}
                              )}
                item_cache[None] = None

                for item in seats_qs:
                    product = item_cache[item['product']]
                    if item_cache[item['product']] not in ctx['seats']['products']:
                        price = None
                        if product and product.has_variations:
                            price = product.variations.filter(
                                active=True
                            ).aggregate(Min('default_price'))['default_price__min']
                        if product and not price:
                            price = product.default_price
                        if not price:
                            price = Decimal('0.00')

                        ctx['seats']['products'][product] = {
                            'free': {
                                'seats': 0,
                                'potential': Decimal('0.00'),
                            },
                            'blocked': {
                                'seats': 0,
                                'potential': Decimal('0.00'),
                            },
                            'price': price,
                        }
                    data = ctx['seats']['products'][product]

                    if item['blocked']:
                        data['blocked']['seats'] = item['count']
                        data['blocked']['potential'] = item['count'] * data['price']
                    else:
                        data['free']['seats'] = item['count']
                        data['free']['potential'] = item['count'] * data['price']

        return ctx
