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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jan Felix Wiebe, Mohit Jindal
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import calendar
import hashlib
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

import isoweek
import pytz
from django.conf import settings
from django.core.cache import caches
from django.db.models import Exists, Max, Min, OuterRef, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.formats import date_format, get_format
from django.utils.timezone import get_current_timezone, now
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.generic import ListView, TemplateView
from pytz import UTC

from pretix.base.i18n import language
from pretix.base.models import (
    Event, EventMetaValue, Quota, SubEvent, SubEventMetaValue,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.helpers.compat import date_fromisocalendar
from pretix.helpers.daterange import daterange
from pretix.helpers.formats.de.formats import WEEK_FORMAT
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
        qs = qs.filter(sales_channels__contains=self.request.sales_channel.identifier)
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
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            active=True,
            is_public=True,
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
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            organizer=self.request.organizer,
            live=True,
            is_public=True,
            has_subevents=False
        ), self.request).order_by('date_from').first()
        next_sev = filter_qs_by_attr(SubEvent.objects.using(settings.DATABASE_REPLICA).filter(
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
            active=True,
            is_public=True,
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

    def _set_week_to_next_subevent(self):
        tz = pytz.timezone(self.request.event.settings.timezone)
        next_sev = self.request.event.subevents.using(settings.DATABASE_REPLICA).filter(
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            active=True,
            is_public=True,
        ).select_related('event').order_by('date_from').first()

        if next_sev:
            datetime_from = next_sev.date_from
            self.year = datetime_from.astimezone(tz).isocalendar()[0]
            self.week = datetime_from.astimezone(tz).isocalendar()[1]
        else:
            self.year = now().isocalendar()[0]
            self.week = now().isocalendar()[1]

    def _set_week_to_next_event(self):
        next_ev = filter_qs_by_attr(Event.objects.using(settings.DATABASE_REPLICA).filter(
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            organizer=self.request.organizer,
            live=True,
            is_public=True,
            has_subevents=False
        ), self.request).order_by('date_from').first()
        next_sev = filter_qs_by_attr(SubEvent.objects.using(settings.DATABASE_REPLICA).filter(
            Q(date_from__gte=now()) | Q(date_to__isnull=False, date_to__gte=now()),
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
            active=True,
            is_public=True,
        ), self.request).select_related('event').order_by('date_from').first()

        datetime_from = None
        if (next_ev and next_sev and next_sev.date_from < next_ev.date_from) or (next_sev and not next_ev):
            datetime_from = next_sev.date_from
            next_ev = next_sev.event
        elif next_ev:
            datetime_from = next_ev.date_from

        if datetime_from:
            tz = pytz.timezone(next_ev.settings.timezone)
            self.year = datetime_from.astimezone(tz).isocalendar()[0]
            self.week = datetime_from.astimezone(tz).isocalendar()[1]
        else:
            self.year = now().isocalendar()[0]
            self.week = now().isocalendar()[1]

    def _set_week_year(self):
        if hasattr(self.request, 'event') and self.subevent:
            tz = pytz.timezone(self.request.event.settings.timezone)
            self.year = self.subevent.date_from.astimezone(tz).year
            self.month = self.subevent.date_from.astimezone(tz).month
        if 'year' in self.request.GET and 'week' in self.request.GET:
            try:
                self.year = int(self.request.GET.get('year'))
                self.week = int(self.request.GET.get('week'))
            except ValueError:
                self.year = now().isocalendar()[0]
                self.week = now().isocalendar()[1]
        else:
            if hasattr(self.request, 'event'):
                self._set_week_to_next_subevent()
            else:
                self._set_week_to_next_event()


class OrganizerIndex(OrganizerViewMixin, EventListMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'pretixpresale/organizers/index.html'
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        # In stock pretix, nothing on this page is session-dependent except for the language and the customer login part,
        # so we can cache pretty aggressively if the user is anonymous. Note that we deliberately implement the caching
        # on the view layer, *after* all middlewares have been ran, so we have access to the computed locale, as well
        # as the login status etc.
        cache_allowed = (
            settings.CACHE_LARGE_VALUES_ALLOWED and
            not getattr(request, 'customer', None) and
            not request.user.is_authenticated
        )

        if not cache_allowed:
            return super().dispatch(request, *args, **kwargs)

        cache_key_parts = [
            request.method,
            request.host,
            str(request.organizer.pk),
            request.get_full_path(),
            request.LANGUAGE_CODE,
            self.request.sales_channel.identifier,
        ]
        for c, v in request.COOKIES.items():
            # If the cookie is not one we know, it might be set by a plugin and we need to include it in the
            # cache key to be safe. A known example includes plugins that e.g. store cookie banner state.
            if c not in (settings.SESSION_COOKIE_NAME, settings.LANGUAGE_COOKIE_NAME, settings.CSRF_COOKIE_NAME) and not c.startswith('__'):
                cache_key_parts.append(f'{c}={v}')
        for c, v in request.session.items():
            # If the session key is not one we know, it might be set by a plugin and we need to include it in the
            # cache key to be safe. A known example would be the pretix-campaigns plugin setting the campaign ID.
            if (
                    not c.startswith('_auth') and
                    not c.startswith('pretix_auth_') and
                    not c.startswith('customer_auth_') and
                    not c.startswith('current_cart_') and
                    not c.startswith('cart_') and
                    not c.startswith('payment_') and
                    c not in ('carts', 'payment', 'pinned_user_agent')
            ):
                cache_key_parts.append(f'{c}={repr(v)}')

        cache_key = f'pretix.presale.views.organizer.OrganizerIndex:{hashlib.md5(":".join(cache_key_parts).encode()).hexdigest()}'
        cache_timeout = 15
        cache = caches[settings.CACHE_LARGE_VALUES_ALIAS]

        response = cache.get(cache_key)
        if response is not None:
            return response

        response = super().dispatch(request, *kwargs, **kwargs)
        if response.status_code >= 400:
            return response

        if hasattr(response, 'render') and callable(response.render):
            def _store_to_cache(r):
                cache.set(cache_key, r, cache_timeout)

            response.add_post_render_callback(_store_to_cache)
        else:
            cache.set(cache_key, response, cache_timeout)
        return response

    def get(self, request, *args, **kwargs):
        style = request.GET.get("style", request.organizer.settings.event_list_type)
        if style == "calendar":
            cv = CalendarView()
            cv.request = request
            return cv.get(request, *args, **kwargs)
        elif style == "week":
            cv = WeekCalendarView()
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


def has_before_after(eventqs, subeventqs, before, after):
    eqs = eventqs.filter(is_public=True, live=True, has_subevents=False)
    sqs = subeventqs.filter(active=True, is_public=True)
    return (
        eqs.filter(Q(date_from__lte=before)).exists() or sqs.filter(Q(date_from__lte=before)).exists(),
        eqs.filter(Q(date_to__gte=after) | Q(date_from__gte=after)).exists() or sqs.filter(Q(date_to__gte=after) | Q(date_from__gte=after)).exists()
    )


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
            datetime_to = event.date_to.astimezone(tz)
            date_to = event.date_to.astimezone(tz).date()
            d = max(date_from, before.date())
            while d <= date_to and d <= after.date():
                first = d == date_from
                ebd[d].append({
                    'event': event,
                    'continued': not first,
                    'time': datetime_from.time().replace(tzinfo=None) if first and event.settings.show_times else None,
                    'time_end': (
                        datetime_to.time().replace(tzinfo=None)
                        if (date_to == date_from or (
                            date_to == date_from + timedelta(days=1) and datetime_to.time() < datetime_from.time()
                        )) and event.settings.show_times
                        else None
                    ),
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


def add_subevents_for_days(qs, before, after, ebd, timezones, event=None, cart_namespace=None, voucher=None):
    qs = qs.filter(active=True, is_public=True).filter(
        Q(Q(date_to__gte=before) & Q(date_from__lte=after)) |
        Q(Q(date_from__lte=after) & Q(date_to__gte=before)) |
        Q(Q(date_to__isnull=True) & Q(date_from__gte=before) & Q(date_from__lte=after))
    ).order_by(
        'date_from'
    )

    quotas_to_compute = []
    for se in qs:
        if se.presale_is_running:
            quotas_to_compute += se.active_quotas

    name = None
    qcache = {}
    if quotas_to_compute:
        qa = QuotaAvailability()
        qa.queue(*quotas_to_compute)
        qa.compute(allow_cache=True)
        qcache.update(qa.results)

    for se in qs:
        if qcache:
            se._quota_cache = qcache
        kwargs = {'subevent': se.pk}
        if cart_namespace:
            kwargs['cart_namespace'] = cart_namespace

        s = event.settings if event else se.event.settings

        if s.event_list_available_only:
            hide = se.presale_has_ended or (
                (not voucher or not voucher.allow_ignore_quota) and
                se.best_availability_state is not None and
                se.best_availability_state < Quota.AVAILABILITY_RESERVED
            )
            if hide:
                continue

        timezones.add(s.timezones)
        tz = pytz.timezone(s.timezone)
        datetime_from = se.date_from.astimezone(tz)
        date_from = datetime_from.date()
        if name is None:
            name = str(se.name)
        elif str(se.name) != name:
            ebd['_subevents_different_names'] = True
        if s.show_date_to and se.date_to:
            datetime_to = se.date_to.astimezone(tz)
            date_to = se.date_to.astimezone(tz).date()
            d = max(date_from, before.date())
            while d <= date_to and d <= after.date():
                first = d == date_from
                ebd[d].append({
                    'continued': not first,
                    'timezone': s.timezone,
                    'time': datetime_from.time().replace(tzinfo=None) if first and s.show_times else None,
                    'time_end': (
                        datetime_to.time().replace(tzinfo=None)
                        if (date_to == date_from or (
                            date_to == date_from + timedelta(days=1) and datetime_to.time() < datetime_from.time()
                        )) and s.show_times
                        else None
                    ),
                    'event': se,
                    'url': (
                        eventreverse(se.event, 'presale:event.redeem',
                                     kwargs={k: v for k, v in kwargs.items() if k != 'subevent'}) + f'?subevent={se.pk}&voucher={quote(voucher.code)}'
                        if voucher
                        else eventreverse(se.event, 'presale:event.index', kwargs=kwargs)
                    )
                })
                d += timedelta(days=1)

        else:
            ebd[date_from].append({
                'event': se,
                'continued': False,
                'time': datetime_from.time().replace(tzinfo=None) if s.show_times else None,
                'url': (
                    eventreverse(se.event, 'presale:event.redeem',
                                 kwargs={k: v for k, v in kwargs.items() if k != 'subevent'}) + f'?subevent={se.pk}&voucher={quote(voucher.code)}'
                    if voucher
                    else eventreverse(se.event, 'presale:event.index', kwargs=kwargs)
                ),
                'timezone': s.timezone,
            })


def sort_ev(e):
    return e['time'] or time(0, 0, 0), str(e['event'])


def days_for_template(ebd, week):
    day_format = get_format('WEEK_DAY_FORMAT')
    if day_format == 'WEEK_DAY_FORMAT':
        day_format = 'SHORT_DATE_FORMAT'
    return [
        {
            'day_formatted': date_format(day, day_format),
            'date': day,
            'today': day == now().astimezone(get_current_timezone()).date(),
            'events': sorted(ebd.get(day), key=sort_ev) if day in ebd else []
        }
        for day in week.days()
    ]


def weeks_for_template(ebd, year, month):
    calendar.setfirstweekday(0)  # TODO: Configurable
    return [
        [
            {
                'day': day,
                'date': date(year, month, day),
                'events': (
                    sorted(ebd.get(date(year, month, day)), key=sort_ev)
                    if date(year, month, day) in ebd else None
                )
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

        ctx['has_before'], ctx['has_after'] = has_before_after(
            self.request.organizer.events.filter(
                sales_channels__contains=self.request.sales_channel.identifier
            ),
            SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__is_public=True,
                event__live=True,
                event__sales_channels__contains=self.request.sales_channel.identifier
            ),
            before,
            after,
        )

        ctx['multiple_timezones'] = self._multiple_timezones
        ctx['weeks'] = weeks_for_template(ebd, self.year, self.month)
        ctx['months'] = [date(self.year, i + 1, 1) for i in range(12)]
        ctx['years'] = range(now().year - 2, now().year + 3)

        return ctx

    def _events_by_day(self, before, after):
        ebd = defaultdict(list)
        timezones = set()
        add_events_for_days(self.request, Event.annotated(self.request.organizer.events, 'web').using(
            settings.DATABASE_REPLICA
        ).filter(
            sales_channels__contains=self.request.sales_channel.identifier
        ), before, after, ebd, timezones)
        add_subevents_for_days(filter_qs_by_attr(SubEvent.annotated(SubEvent.objects.filter(
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
            event__sales_channels__contains=self.request.sales_channel.identifier
        ).prefetch_related(
            'event___settings_objects', 'event__organizer___settings_objects'
        )), self.request).using(settings.DATABASE_REPLICA), before, after, ebd, timezones)
        self._multiple_timezones = len(timezones) > 1
        return ebd


class WeekCalendarView(OrganizerViewMixin, EventListMixin, TemplateView):
    template_name = 'pretixpresale/organizers/calendar_week.html'

    def get(self, request, *args, **kwargs):
        self._set_week_year()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        week = isoweek.Week(self.year, self.week)
        before = datetime(
            week.monday().year, week.monday().month, week.monday().day, 0, 0, 0, tzinfo=UTC
        ) - timedelta(days=1)
        after = datetime(
            week.sunday().year, week.sunday().month, week.sunday().day, 0, 0, 0, tzinfo=UTC
        ) + timedelta(days=1)

        ctx['date'] = week.monday()
        ctx['before'] = before
        ctx['after'] = after

        ebd = self._events_by_day(before, after)

        ctx['has_before'], ctx['has_after'] = has_before_after(
            self.request.organizer.events.filter(
                sales_channels__contains=self.request.sales_channel.identifier
            ),
            SubEvent.objects.filter(
                event__organizer=self.request.organizer,
                event__is_public=True,
                event__live=True,
                event__sales_channels__contains=self.request.sales_channel.identifier
            ),
            before,
            after,
        )

        ctx['days'] = days_for_template(ebd, week)
        ctx['weeks'] = [
            (date_fromisocalendar(self.year, i + 1, 1), date_fromisocalendar(self.year, i + 1, 7))
            for i in range(53 if date(self.year, 12, 31).isocalendar()[1] == 53 else 52)
        ]
        ctx['years'] = range(now().year - 2, now().year + 3)
        ctx['week_format'] = get_format('WEEK_FORMAT')
        if ctx['week_format'] == 'WEEK_FORMAT':
            ctx['week_format'] = WEEK_FORMAT
        ctx['multiple_timezones'] = self._multiple_timezones

        return ctx

    def _events_by_day(self, before, after):
        ebd = defaultdict(list)
        timezones = set()
        add_events_for_days(self.request, Event.annotated(self.request.organizer.events, 'web').using(
            settings.DATABASE_REPLICA
        ).filter(
            sales_channels__contains=self.request.sales_channel.identifier
        ), before, after, ebd, timezones)
        add_subevents_for_days(filter_qs_by_attr(SubEvent.annotated(SubEvent.objects.filter(
            event__organizer=self.request.organizer,
            event__is_public=True,
            event__live=True,
            event__sales_channels__contains=self.request.sales_channel.identifier
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
                self.request.organizer.events.filter(
                    is_public=True,
                    live=True,
                    has_subevents=False,
                    sales_channels__contains=self.request.sales_channel.identifier
                ),
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
                    active=True,
                    event__sales_channels__contains=self.request.sales_channel.identifier
                ),
                request
            ).prefetch_related(
                'event___settings_objects', 'event__organizer___settings_objects'
            ).order_by(
                'date_from'
            )
        )

        if 'locale' in request.GET and request.GET.get('locale') in dict(settings.LANGUAGES):
            with language(request.GET.get('locale'), self.request.organizer.settings.region):
                cal = get_ical(events)
        else:
            cal = get_ical(events)

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}.ics"'.format(
            request.organizer.slug
        )
        if request.organizer.settings.meta_noindex:
            resp['X-Robots-Tag'] = 'noindex'
        return resp
