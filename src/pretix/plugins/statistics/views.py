import datetime
import json

import dateutil.parser
import dateutil.rrule
from django.db.models import Count
from django.views.generic import TemplateView

from pretix.base.models import Order
from pretix.control.permissions import EventPermissionRequiredMixin


class IndexView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/statistics/index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ordered_by_day = {
            (o['datetime'] if isinstance(o['datetime'], datetime.date) else dateutil.parser.parse(o['datetime'])).date(): o['count']
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

        return ctx
