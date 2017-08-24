import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

import pytz
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.generic import ListView, TemplateView
from pytz import UTC

from pretix.base.i18n import language
from pretix.base.models import Event, SubEvent
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_ical
from pretix.presale.views import OrganizerViewMixin


class OrganizerIndex(OrganizerViewMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'pretixpresale/organizers/index.html'
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        style = request.GET.get("style", request.organizer.settings.event_list_type)
        if style == "calendar":
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


def add_events_for_days(organizer, before, after, ebd, timezones):
    qs = organizer.events.filter(is_public=True, live=True, has_subevents=False).filter(
        Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
        Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
        Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
    ).order_by(
        'date_from'
    ).prefetch_related(
        '_settings_objects', 'organizer___settings_objects'
    )
    for event in qs:
        timezones.add(event.settings.timezones)
        tz = pytz.timezone(event.settings.timezone)
        datetime_from = event.date_from.astimezone(tz)
        date_from = datetime_from.date()
        if event.settings.show_date_to and event.date_to:
            date_to = event.date_to.astimezone(tz).date()
            d = max(date_from, before.date())
            while d <= date_to and d <= after.date():
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


def add_subevents_for_days(qs, before, after, ebd, timezones, event=None):
    qs = qs.filter(active=True).filter(
        Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
        Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
        Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
    ).order_by(
        'date_from'
    )
    for se in qs:
        settings = event.settings if event else se.event.settings
        timezones.add(settings.timezones)
        tz = pytz.timezone(settings.timezone)
        datetime_from = se.date_from.astimezone(tz)
        date_from = datetime_from.date()
        if se.event.settings.show_date_to and se.date_to:
            date_to = se.date_to.astimezone(tz).date()
            d = max(date_from, before.date())
            while d <= date_to and d <= after.date():
                first = d == date_from
                ebd[d].append({
                    'continued': not first,
                    'timezone': settings.timezone,
                    'time': datetime_from.time().replace(tzinfo=None) if first and settings.show_times else None,
                    'event': se,
                    'url': eventreverse(se.event, 'presale:event.index', kwargs={
                        'subevent': se.pk
                    }),
                })
                d += timedelta(days=1)

        else:
            ebd[date_from].append({
                'event': se,
                'continued': False,
                'time': datetime_from.time().replace(tzinfo=None) if se.event.settings.show_times else None,
                'url': eventreverse(se.event, 'presale:event.index', kwargs={
                    'subevent': se.pk
                }),
                'timezone': se.event.settings.timezone,
            })


def weeks_for_template(ebd, year, month):
    calendar.setfirstweekday(0)  # TODO: Configurable
    return [
        [
            {
                'day': day,
                'date': date(year, month, day),
                'events': ebd.get(date(year, month, day))
            }
            if day > 0
            else None
            for day in week
        ]
        for week in calendar.monthcalendar(year, month)
    ]


class CalendarView(OrganizerViewMixin, TemplateView):
    template_name = 'pretixpresale/organizers/calendar.html'

    def get(self, request, *args, **kwargs):
        if 'year' in kwargs and 'month' in kwargs:
            self.year = int(kwargs.get('year'))
            self.month = int(kwargs.get('month'))
        elif 'year' in request.GET and 'month' in request.GET:
            try:
                self.year = int(request.GET.get('year'))
                self.month = int(request.GET.get('month'))
            except ValueError:
                self.year = now().year
                self.month = now().month
        else:
            next_ev = Event.objects.filter(
                live=True,
                is_public=True,
                date_from__gte=now(),
                has_subevents=False
            ).order_by('date_from').first()
            next_sev = SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__is_public=True,
                event__live=True,
                active=True,
                date_from__gte=now()
            ).select_related('event').order_by('date_from').first()

            datetime_from = None
            if (next_ev and next_sev and next_sev.date_from < next_ev.date_from) or (next_sev and not next_ev):
                datetime_from = next_sev.date_from
                next_ev = next_sev.event
            elif next_ev:
                datetime_from = next_ev.date_from

            if datetime_from:
                tz = pytz.timezone(next_ev.settings.timezone)
                self.year = datetime_from.astimezone(tz).year
                self.month = datetime_from.astimezone(tz).month
            else:
                self.year = now().year
                self.month = now().month
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        _, ndays = calendar.monthrange(self.year, self.month)
        before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=UTC) - timedelta(days=1)
        after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=UTC) + timedelta(days=1)

        ctx['date'] = date(self.year, self.month, 1)
        ctx['before'] = before
        ctx['after'] = after
        ebd = self._events_by_day(before, after)

        ctx['multiple_timezones'] = self._multiple_timezones
        ctx['weeks'] = weeks_for_template(ebd, self.year, self.month)
        ctx['months'] = [date(self.year, i + 1, 1) for i in range(12)]
        ctx['years'] = range(now().year - 2, now().year + 3)

        return ctx

    def _events_by_day(self, before, after):
        ebd = defaultdict(list)
        timezones = set()
        add_events_for_days(self.request.organizer, before, after, ebd, timezones)
        add_subevents_for_days(SubEvent.objects.filter(
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
        ).prefetch_related(
            'event___settings_objects', 'event__organizer___settings_objects'
        ), before, after, ebd, timezones)
        self._multiple_timezones = len(timezones) > 1
        return ebd


@method_decorator(cache_page(300), name='dispatch')
class OrganizerIcalDownload(OrganizerViewMixin, View):
    def get(self, request, *args, **kwargs):
        events = list(
            self.request.organizer.events.filter(is_public=True, live=True, has_subevents=False).order_by(
                'date_from'
            ).prefetch_related(
                '_settings_objects', 'organizer___settings_objects'
            )
        )
        events += list(
            SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__is_public=True,
                event__live=True,
                active=True
            ).prefetch_related(
                'event___settings_objects', 'event__organizer___settings_objects'
            ).order_by(
                'date_from'
            )
        )

        if 'locale' in request.GET and request.GET.get('locale') in dict(settings.LANGUAGES):
            with language(request.GET.get('locale')):
                cal = get_ical(events)
        else:
            cal = get_ical(events)

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}.ics"'.format(
            request.organizer.slug
        )
        return resp
