import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

import pytz
from django.conf import settings
from django.db.models import Exists, Max, Min, OuterRef, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.generic import ListView, TemplateView
from pytz import UTC

from pretix.base.i18n import language
from pretix.base.models import (
    Event, EventMetaValue, SubEvent, SubEventMetaValue,
)
from pretix.helpers.daterange import daterange
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_ical
from pretix.presale.views import OrganizerViewMixin


def filter_qs_by_attr(qs, request):
    """
    We'll allow to filter the event list using attributes defined in the event meta data
    models in the format ?attr[meta_name]=meta_value
    """
    attrs = {}
    for i, item in enumerate(request.GET.items()):
        k, v = item
        if k.startswith("attr[") and k.endswith("]"):
            attrs[k[5:-1]] = v

    skey = 'filter_qs_by_attr_{}_{}'.format(request.organizer.pk, request.event.pk if hasattr(request, 'event') else '')
    if request.GET.get('attr_persist'):
        request.session[skey] = attrs
    elif skey in request.session:
        attrs = request.session[skey]

    props = {
        p.name: p for p in request.organizer.meta_properties.filter(
            name__in=attrs.keys()
        )
    }

    for i, item in enumerate(attrs.items()):
        attr, v = item
        emv_with_value = EventMetaValue.objects.filter(
            event=OuterRef('event' if qs.model == SubEvent else 'pk'),
            property__name=attr,
            value=v
        )
        emv_with_any_value = EventMetaValue.objects.filter(
            event=OuterRef('event' if qs.model == SubEvent else 'pk'),
            property__name=attr,
        )
        if qs.model == SubEvent:
            semv_with_value = SubEventMetaValue.objects.filter(
                subevent=OuterRef('pk'),
                property__name=attr,
                value=v
            )
            semv_with_any_value = SubEventMetaValue.objects.filter(
                subevent=OuterRef('pk'),
                property__name=attr,
            )

        prop = props.get(attr)
        if not prop:
            continue
        annotations = {'attr_{}'.format(i): Exists(emv_with_value)}
        if qs.model == SubEvent:
            annotations['attr_{}_sub'.format(i)] = Exists(semv_with_value)
            annotations['attr_{}_sub_any'.format(i)] = Exists(semv_with_any_value)
            filters = Q(**{'attr_{}_sub'.format(i): True})
            filters |= Q(Q(**{'attr_{}_sub_any'.format(i): False}) & Q(**{'attr_{}'.format(i): True}))
            if prop.default == v:
                annotations['attr_{}_any'.format(i)] = Exists(emv_with_any_value)
                filters |= Q(Q(**{'attr_{}_sub_any'.format(i): False}) & Q(**{'attr_{}_any'.format(i): False}))
        else:
            filters = Q(**{'attr_{}'.format(i): True})
            if prop.default == v:
                annotations['attr_{}_any'.format(i)] = Exists(emv_with_any_value)
                filters |= Q(**{'attr_{}_any'.format(i): False})

        qs = qs.annotate(**annotations).filter(filters)
    return qs


class EventListMixin:

    def _get_event_queryset(self):
        query = Q(is_public=True) & Q(live=True)
        qs = self.request.organizer.events.using(settings.DATABASE_REPLICA).filter(query)
        qs = qs.annotate(
            min_from=Min('subevents__date_from'),
            min_to=Min('subevents__date_to'),
            max_from=Max('subevents__date_from'),
            max_to=Max('subevents__date_to'),
            max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from')),
        )
        if "old" in self.request.GET:
            qs = qs.filter(
                Q(Q(has_subevents=False) & Q(
                    Q(date_to__lt=now()) | Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
                )) | Q(Q(has_subevents=True) & Q(
                    Q(min_to__lt=now()) | Q(min_from__lt=now()))
                )
            ).annotate(
                order_to=Coalesce('max_fromto', 'max_to', 'max_from', 'date_to', 'date_from'),
            ).order_by('-order_to')
        else:
            qs = qs.filter(
                Q(Q(has_subevents=False) & Q(
                    Q(date_to__gte=now()) | Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                )) | Q(Q(has_subevents=True) & Q(
                    Q(max_to__gte=now()) | Q(max_from__gte=now()))
                )
            ).annotate(
                order_from=Coalesce('min_from', 'date_from'),
            ).order_by('order_from')
        qs = Event.annotated(filter_qs_by_attr(qs, self.request))
        return qs

    def _set_month_to_next_subevent(self):
        tz = pytz.timezone(self.request.event.settings.timezone)
        next_sev = self.request.event.subevents.using(settings.DATABASE_REPLICA).filter(
            active=True,
            is_public=True,
            date_from__gte=now()
        ).select_related('event').order_by('date_from').first()

        if next_sev:
            datetime_from = next_sev.date_from
            self.year = datetime_from.astimezone(tz).year
            self.month = datetime_from.astimezone(tz).month
        else:
            self.year = now().year
            self.month = now().month

    def _set_month_to_next_event(self):
        next_ev = filter_qs_by_attr(Event.objects.using(settings.DATABASE_REPLICA).filter(
            organizer=self.request.organizer,
            live=True,
            is_public=True,
            date_from__gte=now(),
            has_subevents=False
        ), self.request).order_by('date_from').first()
        next_sev = filter_qs_by_attr(SubEvent.objects.using(settings.DATABASE_REPLICA).filter(
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
            active=True,
            is_public=True,
            date_from__gte=now()
        ), self.request).select_related('event').order_by('date_from').first()

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

    def _set_month_year(self):
        if hasattr(self.request, 'event') and self.subevent:
            tz = pytz.timezone(self.request.event.settings.timezone)
            self.year = self.subevent.date_from.astimezone(tz).year
            self.month = self.subevent.date_from.astimezone(tz).month
        if 'year' in self.request.GET and 'month' in self.request.GET:
            try:
                self.year = int(self.request.GET.get('year'))
                self.month = int(self.request.GET.get('month'))
            except ValueError:
                self.year = now().year
                self.month = now().month
        else:
            if hasattr(self.request, 'event'):
                self._set_month_to_next_subevent()
            else:
                self._set_month_to_next_event()


class OrganizerIndex(OrganizerViewMixin, EventListMixin, ListView):
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
        return self._get_event_queryset()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for event in ctx['events']:
            event.tzname = pytz.timezone(event.cache.get_or_set('timezone', lambda: event.settings.timezone))
            if event.has_subevents:
                event.daterange = daterange(
                    event.min_from.astimezone(event.tzname),
                    (event.max_fromto or event.max_to or event.max_from).astimezone(event.tzname)
                )
        return ctx


def add_events_for_days(request, baseqs, before, after, ebd, timezones):
    qs = baseqs.filter(is_public=True, live=True, has_subevents=False).filter(
        Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
        Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
        Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
    ).order_by(
        'date_from'
    ).prefetch_related(
        '_settings_objects', 'organizer___settings_objects'
    )
    if hasattr(request, 'organizer'):
        qs = filter_qs_by_attr(qs, request)
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


def add_subevents_for_days(qs, before, after, ebd, timezones, event=None, cart_namespace=None):
    qs = qs.filter(active=True, is_public=True).filter(
        Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
        Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
        Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
    ).order_by(
        'date_from'
    )
    for se in qs:
        kwargs = {'subevent': se.pk}
        if cart_namespace:
            kwargs['cart_namespace'] = cart_namespace

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
                    'url': eventreverse(se.event, 'presale:event.index', kwargs=kwargs)
                })
                d += timedelta(days=1)

        else:
            ebd[date_from].append({
                'event': se,
                'continued': False,
                'time': datetime_from.time().replace(tzinfo=None) if se.event.settings.show_times else None,
                'url': eventreverse(se.event, 'presale:event.index', kwargs=kwargs),
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


class CalendarView(OrganizerViewMixin, EventListMixin, TemplateView):
    template_name = 'pretixpresale/organizers/calendar.html'

    def get(self, request, *args, **kwargs):
        self._set_month_year()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        try:
            _, ndays = calendar.monthrange(self.year, self.month)
        except calendar.IllegalMonthError:
            raise Http404()
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
        add_events_for_days(self.request, Event.annotated(self.request.organizer.events, 'web').using(settings.DATABASE_REPLICA), before, after, ebd, timezones)
        add_subevents_for_days(filter_qs_by_attr(SubEvent.annotated(SubEvent.objects.filter(
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
        ).prefetch_related(
            'event___settings_objects', 'event__organizer___settings_objects'
        )), self.request).using(settings.DATABASE_REPLICA), before, after, ebd, timezones)
        self._multiple_timezones = len(timezones) > 1
        return ebd


@method_decorator(cache_page(300), name='dispatch')
class OrganizerIcalDownload(OrganizerViewMixin, View):
    def get(self, request, *args, **kwargs):
        events = list(
            filter_qs_by_attr(
                self.request.organizer.events.filter(is_public=True, live=True, has_subevents=False),
                request
            ).order_by(
                'date_from'
            ).prefetch_related(
                '_settings_objects', 'organizer___settings_objects'
            )
        )
        events += list(
            filter_qs_by_attr(
                SubEvent.objects.filter(
                    event__organizer=self.request.organizer,
                    event__is_public=True,
                    event__live=True,
                    is_public=True,
                    active=True
                ),
                request
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
