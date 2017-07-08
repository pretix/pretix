import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

import pytz
from django.db.models import Q
from django.utils.timezone import now
from django.views.generic import ListView, TemplateView
from pytz import UTC

from pretix.base.models import Event
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import OrganizerViewMixin


class OrganizerIndex(OrganizerViewMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'pretixpresale/organizers/index.html'
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        if request.organizer.settings.event_list_type == 'calendar':
            cv = CalendarView()
            cv.request = request
            return cv.get(request, *args, **kwargs)
        else:
            return super().get(request, *args, **kwargs)

    def get_queryset(self):
        query = Q(is_public=True) & Q(live=True)
        if "old" in self.request.GET:
            query &= Q(Q(date_from__lte=now()) & Q(date_to__lte=now()))
            order = '-date_from'
        else:
            query &= Q(Q(date_from__gte=now()) | Q(date_to__gte=now()))
            order = 'date_from'
        return Event.objects.filter(
            Q(organizer=self.request.organizer) & query
        ).order_by(order)


class CalendarView(OrganizerViewMixin, TemplateView):
    template_name = 'pretixpresale/organizers/calendar.html'

    def get(self, request, *args, **kwargs):
        if 'year' in kwargs and 'month' in kwargs:
            self.year = int(kwargs.get('year'))
            self.month = int(kwargs.get('month'))
        else:
            next_ev = Event.objects.filter(live=True, is_public=True, date_from__gte=now()).order_by('date_from').first()
            tz = pytz.timezone(next_ev.settings.timezone)
            datetime_from = next_ev.date_from.astimezone(tz)
            self.year = datetime_from.year
            self.month = datetime_from.month
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        _, ndays = calendar.monthrange(self.year, self.month)
        before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=UTC) - timedelta(days=1)
        after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=UTC) + timedelta(days=1)

        ctx['date'] = date(self.year, self.month, 1)
        ctx['before'] = before
        ctx['after'] = after
        ebd = self._events_by_day()

        calendar.setfirstweekday(0)  # TODO: Configurable
        ctx['multiple_timezones'] = self._multiple_timezones
        ctx['weeks'] = [
            [
                {
                    'day': day,
                    'date': date(self.year, self.month, day),
                    'events': ebd[date(self.year, self.month, day)]
                }
                if day > 0
                else None
                for day in week
            ]
            for week in calendar.monthcalendar(self.year, self.month)
        ]

        return ctx

    def _events_by_day(self):
        _, ndays = calendar.monthrange(self.year, self.month)
        before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=UTC) - timedelta(days=1)
        after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=UTC) + timedelta(days=1)
        ebd = defaultdict(list)
        qs = self.request.organizer.events.filter(is_public=True, live=True).filter(
            Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
            Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
            Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
        ).order_by(
            'date_from'
        ).prefetch_related(
            '_settings_objects', 'organizer___settings_objects'
        )
        timezones = set()
        for event in qs:
            timezones.add(event.settings.timezones)
            tz = pytz.timezone(event.settings.timezone)
            datetime_from = event.date_from.astimezone(tz)
            date_from = datetime_from.date()
            if event.settings.show_date_to and event.date_to:
                date_to = event.date_to.astimezone(tz).date()
                d = date_from
                while d <= date_to:
                    first = d == date_from
                    ebd[d].append({
                        'event': event,
                        'continued': not first,
                        'time': datetime_from.time().replace(tzinfo=None) if first and event.settings.show_times else None,
                        'url': eventreverse(event, 'presale:event.index'),
                        'timezone': event.settings.timezone,
                    })
                    d += timedelta(days=1)

            else:
                ebd[date_from].append({
                    'event': event,
                    'continued': False,
                    'time': datetime_from.time().replace(tzinfo=None) if event.settings.show_times else None,
                    'url': eventreverse(event, 'presale:event.index'),
                    'timezone': event.settings.timezone,
                })

        self._multiple_timezones = len(timezones) > 1
        return ebd
