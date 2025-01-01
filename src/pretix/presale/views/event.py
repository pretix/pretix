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
# This file contains Apache-licensed contributions copyrighted by: Vishal Sodani, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import calendar
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from urllib.parse import urlencode

import isoweek
from dateutil import parser
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.formats import get_format
from django.utils.functional import SimpleLazyObject
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import get_current_timezone, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import Quota, Voucher
from pretix.base.models.event import Event, SubEvent
from pretix.base.services.placeholders import PlaceholderContext
from pretix.base.timemachine import (
    has_time_machine_permission, time_machine_now,
)
from pretix.helpers.compat import date_fromisocalendar
from pretix.helpers.formats.en.formats import (
    SHORT_MONTH_DAY_FORMAT, WEEK_FORMAT,
)
from pretix.helpers.http import redirect_to_url
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.ical import get_public_ical
from pretix.presale.signals import seatingframe_html_head
from pretix.presale.views.organizer import (
    EventListMixin, add_subevents_for_days, days_for_template,
    filter_qs_by_attr, has_before_after, weeks_for_template,
)

from ...base.storelogic.products import (
    get_items_for_product_list, item_group_by_category,
)
from . import (
    CartMixin, EventViewMixin, allow_frame_if_namespaced, get_cart,
    iframe_entry_view_wrapper,
)

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class EventIndex(EventViewMixin, EventListMixin, CartMixin, TemplateView):
    template_name = "pretixpresale/event/index.html"

    def get(self, request, *args, **kwargs):
        # redirect old month-year-URLs to new date-URLs
        keys = ("month", "year")
        if all(k in request.GET for k in keys):
            get_params = {k: v for k, v in request.GET.items() if k not in keys}
            get_params["date"] = "%s-%s" % (request.GET.get("year"), request.GET.get("month"))
            return redirect_to_url(self.request.path + "?" + urlencode(get_params))

        # redirect old week-year-URLs to new date-URLs
        keys = ("week", "year")
        if all(k in request.GET for k in keys):
            get_params = {k: v for k, v in request.GET.items() if k not in keys}
            get_params["date"] = "%s-W%s" % (request.GET.get("year"), request.GET.get("week"))
            return redirect_to_url(self.request.path + "?" + urlencode(get_params))

        from pretix.presale.views.cart import get_or_create_cart_id

        self.subevent = None
        utm_params = {k: v for k, v in request.GET.items() if k.startswith("utm_")}
        if request.GET.get('src', '') == 'widget' and 'take_cart_id' in request.GET:
            # User has clicked "Open in a new tab" link in widget
            get_or_create_cart_id(request)
            return redirect_to_url(eventreverse(request.event, 'presale:event.index', kwargs=kwargs) + '?' + urlencode(utm_params))
        elif request.GET.get('iframe', '') == '1' and 'take_cart_id' in request.GET:
            # Widget just opened, a cart already exists. Let's to a stupid redirect to check if cookies are disabled
            get_or_create_cart_id(request)
            return redirect_to_url(eventreverse(request.event, 'presale:event.index', kwargs=kwargs) + '?' + urlencode({
                'require_cookie': 'true',
                'cart_id': request.GET.get('take_cart_id'),
                **({"locale": request.GET.get('locale')} if request.GET.get('locale') else {}),
                **utm_params,
            }))
        elif request.GET.get('iframe', '') == '1' and len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)
        elif 'require_cookie' in request.GET and settings.SESSION_COOKIE_NAME not in request.COOKIES and \
                '__Host-' + settings.SESSION_COOKIE_NAME not in self.request.COOKIES:
            # Cookies are in fact not supported
            r = render(request, 'pretixpresale/event/cookies.html', {
                'url': eventreverse(
                    request.event, "presale:event.index", kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''}
                ) + "?" + urlencode({
                    "src": "widget",
                    **({"locale": request.GET.get('locale')} if request.GET.get('locale') else {}),
                    **({"take_cart_id": request.GET.get('cart_id')} if request.GET.get('cart_id') else {}),
                    **utm_params,
                })
            })
            r._csp_ignore = True
            return r

        if not request.event.all_sales_channels and request.sales_channel.identifier not in (s.identifier for s in request.event.limit_sales_channels.all()):
            raise Http404(_('Tickets for this event cannot be purchased on this sales channel.'))

        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.using(settings.DATABASE_REPLICA).filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent:
                    raise Http404()
                return super().get(request, *args, **kwargs)
            else:
                return super().get(request, *args, **kwargs)
        else:
            if 'subevent' in kwargs:
                return redirect_to_url(self.get_index_url() + '?' + urlencode(utm_params))
            else:
                return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['ev'] = self.subevent or self.request.event
        context['subevent'] = self.subevent
        context['subevent_list_foldable'] = self.subevent and "date" not in self.request.GET and "filtered" not in self.request.GET

        # Show voucher option if an event is selected and vouchers exist
        vouchers_exist = self.request.event.cache.get('vouchers_exist')
        if vouchers_exist is None:
            vouchers_exist = self.request.event.vouchers.exists()
            self.request.event.cache.set('vouchers_exist', vouchers_exist)
        context['show_vouchers'] = context['vouchers_exist'] = vouchers_exist and (
            (self.request.event.has_subevents and not self.subevent) or
            context['ev'].presale_is_running
        )

        context['allow_waitinglist'] = context['ev'].waiting_list_active and context['ev'].presale_is_running

        if not self.request.event.has_subevents or self.subevent:
            # Fetch all items
            items, display_add_to_cart = get_items_for_product_list(
                self.request.event,
                subevent=self.subevent,
                filter_items=self.request.GET.getlist('item'),
                filter_categories=self.request.GET.getlist('category'),
                require_seat=None,
                channel=self.request.sales_channel,
                memberships=(
                    self.request.customer.usable_memberships(
                        for_event=self.subevent or self.request.event,
                        testmode=self.request.event.testmode
                    ) if getattr(self.request, 'customer', None) else None
                ),
            )

            context['waitinglist_seated'] = False
            if context['allow_waitinglist']:
                for i in items:
                    if not i.allow_waitinglist or not i.requires_seat:
                        continue

                    if i.has_variations:
                        for v in i.available_variations:
                            if v.cached_availability[0] != Quota.AVAILABILITY_OK:
                                context['waitinglist_seated'] = True
                                break
                    else:
                        if i.cached_availability[0] != Quota.AVAILABILITY_OK:
                            context['waitinglist_seated'] = True
                            break

            items = [i for i in items if not i.requires_seat]
            context['itemnum'] = len(items)
            context['allfree'] = all(
                item.display_price.gross == Decimal('0.00') and not item.mandatory_priced_addons
                for item in items if not item.has_variations
            ) and all(
                all(
                    var.display_price.gross == Decimal('0.00')
                    for var in item.available_variations
                ) and not item.mandatory_priced_addons
                for item in items if item.has_variations
            )

            # Regroup those by category
            context['items_by_category'] = item_group_by_category(items)
            context['display_add_to_cart'] = display_add_to_cart

        context['cart'] = self.get_cart()
        context['has_addon_choices'] = any(cp.has_addon_choices for cp in get_cart(self.request))

        templating_context = PlaceholderContext(event_or_subevent=self.subevent or self.request.event, event=self.request.event)
        if self.subevent:
            context['frontpage_text'] = templating_context.format(str(self.subevent.frontpage_text))
        else:
            context['frontpage_text'] = templating_context.format(str(self.request.event.settings.frontpage_text))

        if self.request.event.has_subevents:
            context['subevent_list'] = SimpleLazyObject(self._subevent_list_context)
            context['subevent_list_cache_key'] = self._subevent_list_cachekey()

        context['show_cart'] = (
            (context['cart']['positions'] or context['cart'].get('current_selected_payments')) and (
                self.request.event.has_subevents or self.request.event.presale_is_running
            )
        )
        if self.request.event.settings.redirect_to_checkout_directly:
            context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                    kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
            if context['cart_redirect'].startswith('https:'):
                context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]
        else:
            context['cart_redirect'] = self.request.path

        return context

    def _subevent_list_cachekey(self):
        cache_key_parts = [
            self.request.host,
            str(self.request.event.pk),
            self.request.get_full_path(),
            self.request.LANGUAGE_CODE,
            self.request.sales_channel.identifier,
        ]
        cache_key = f'pretix.presale.views.event.EventIndex.subevent_list_context:{hashlib.md5(":".join(cache_key_parts).encode()).hexdigest()}'
        return cache_key

    def _subevent_list_context(self):
        voucher = None
        if self.request.GET.get('voucher'):
            try:
                voucher = Voucher.objects.get(code__iexact=self.request.GET.get('voucher'), event=self.request.event)
            except Voucher.DoesNotExist:
                pass

        context = {}
        context['list_type'] = self.request.GET.get("style", self.request.event.settings.event_list_type)
        if context['list_type'] not in ("calendar", "week") and self.request.event.subevents.filter(date_from__gt=time_machine_now()).count() > 50:
            if self.request.event.settings.event_list_type not in ("calendar", "week"):
                self.request.event.settings.event_list_type = "calendar"
            context['list_type'] = "calendar"

        if context['list_type'] == "calendar":
            self._set_month_year()
            tz = self.request.event.timezone
            _, ndays = calendar.monthrange(self.year, self.month)
            before = datetime(self.year, self.month, 1, 0, 0, 0, tzinfo=tz) - timedelta(days=1)
            after = datetime(self.year, self.month, ndays, 0, 0, 0, tzinfo=tz) + timedelta(days=1)

            if self.request.event.settings.event_calendar_future_only:
                limit_before = time_machine_now().astimezone(tz)
            else:
                limit_before = before

            context['date'] = date(self.year, self.month, 1)
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel,
                        voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                ),
                limit_before, after, ebd, set(), self.request.event,
                self.kwargs.get('cart_namespace'),
                voucher,
            )

            # Hide names of subevents in event series where it is always the same.  No need to show the name of the museum thousands of times
            # in the calendar. We previously only looked at the current time range for this condition which caused weird side-effects, so we need
            # an extra query to look at the entire series. For performance reasons, we have a limit on how many different names we look at.
            context['show_names'] = sum(len(i) for i in ebd.values() if isinstance(i, list)) < 2 or self.request.event.cache.get_or_set(
                'has_different_subevent_names',
                lambda: len(set(str(n) for n in self.request.event.subevents.order_by().values_list('name', flat=True).annotate(c=Count('*'))[:250])) != 1,
                timeout=120,
            )
            context['weeks'] = weeks_for_template(ebd, self.year, self.month, future_only=self.request.event.settings.event_calendar_future_only)
            context['weeks'] = weeks_for_template(ebd, self.year, self.month, future_only=self.request.event.settings.event_calendar_future_only)
            context['months'] = [date(self.year, i + 1, 1) for i in range(12)]
            if self.request.event.settings.event_calendar_future_only:
                context['years'] = range(time_machine_now().year, time_machine_now().year + 3)
            else:
                context['years'] = range(time_machine_now().year - 2, time_machine_now().year + 3)

            context['has_before'], context['has_after'] = has_before_after(
                Event.objects.none(),
                SubEvent.objects.filter(
                    event=self.request.event,
                ),
                before,
                after,
                future_only=self.request.event.settings.event_calendar_future_only
            )
        elif context['list_type'] == "week":
            self._set_week_year()
            tz = self.request.event.timezone
            week = isoweek.Week(self.year, self.week)
            before = datetime(
                week.monday().year, week.monday().month, week.monday().day, 0, 0, 0, tzinfo=tz
            ) - timedelta(days=1)
            after = datetime(
                week.sunday().year, week.sunday().month, week.sunday().day, 0, 0, 0, tzinfo=tz
            ) + timedelta(days=1)

            if self.request.event.settings.event_calendar_future_only:
                limit_before = time_machine_now().astimezone(tz)
            else:
                limit_before = before

            context['date'] = week.monday()
            context['before'] = before
            context['after'] = after

            ebd = defaultdict(list)
            add_subevents_for_days(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel,
                        voucher=voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                ),
                limit_before, after, ebd, set(), self.request.event,
                self.kwargs.get('cart_namespace'),
                voucher,
            )

            # Hide names of subevents in event series where it is always the same.  No need to show the name of the museum thousands of times
            # in the calendar. We previously only looked at the current time range for this condition which caused weird side-effects, so we need
            # an extra query to look at the entire series. For performance reasons, we have a limit on how many different names we look at.
            context['show_names'] = sum(len(i) for i in ebd.values() if isinstance(i, list)) < 2 or self.request.event.cache.get_or_set(
                'has_different_subevent_names',
                lambda: len(set(str(n) for n in self.request.event.subevents.order_by().values_list('name', flat=True).annotate(c=Count('*'))[:250])) != 1,
                timeout=120,
            )
            context['days'] = days_for_template(ebd, week, future_only=self.request.event.settings.event_calendar_future_only)
            years = (self.year - 1, self.year, self.year + 1)
            weeks = []
            for year in years:
                weeks += [
                    (date_fromisocalendar(year, i + 1, 1), date_fromisocalendar(year, i + 1, 7))
                    for i in range(53 if date(year, 12, 31).isocalendar()[1] == 53 else 52)
                    if not self.request.event.settings.event_calendar_future_only or
                    date_fromisocalendar(year, i + 1, 7) > time_machine_now().astimezone(tz).replace(tzinfo=None)
                ]
            context['weeks'] = [[w for w in weeks if w[0].year == year] for year in years]
            context['week_format'] = get_format('WEEK_FORMAT')
            if context['week_format'] == 'WEEK_FORMAT':
                context['week_format'] = WEEK_FORMAT
            context['short_month_day_format'] = get_format('SHORT_MONTH_DAY_FORMAT')
            if context['short_month_day_format'] == 'SHORT_MONTH_DAY_FORMAT':
                context['short_month_day_format'] = SHORT_MONTH_DAY_FORMAT

            context['has_before'], context['has_after'] = has_before_after(
                Event.objects.none(),
                SubEvent.objects.filter(
                    event=self.request.event,
                ),
                before,
                after,
                future_only=self.request.event.settings.event_calendar_future_only
            )
        else:
            context['subevent_list'] = self.request.event.subevents_sorted(
                filter_qs_by_attr(
                    self.request.event.subevents_annotated(
                        self.request.sales_channel,
                        voucher=voucher,
                    ).using(settings.DATABASE_REPLICA),
                    self.request
                )
            )
            if self.request.event.settings.event_list_available_only and not voucher:
                context['subevent_list'] = [
                    se for se in context['subevent_list']
                    if not se.presale_has_ended and (se.best_availability_state is None or se.best_availability_state >= Quota.AVAILABILITY_RESERVED)
                ]
        return context


@method_decorator(allow_frame_if_namespaced, 'dispatch')
@method_decorator(iframe_entry_view_wrapper, 'dispatch')
class SeatingPlanView(EventViewMixin, TemplateView):
    template_name = "pretixpresale/event/seatingplan.html"

    def get(self, request, *args, **kwargs):
        from pretix.presale.views.cart import get_or_create_cart_id

        self.subevent = None
        utm_params = {k: v for k, v in request.GET.items() if k.startswith("utm_")}
        if request.GET.get('src', '') == 'widget' and 'take_cart_id' in request.GET:
            # User has clicked "Open in a new tab" link in widget
            get_or_create_cart_id(request)
            return redirect_to_url(eventreverse(request.event, 'presale:event.seatingplan', kwargs=kwargs) + '?' + urlencode(utm_params))
        elif request.GET.get('iframe', '') == '1' and 'take_cart_id' in request.GET:
            # Widget just opened, a cart already exists. Let's to a stupid redirect to check if cookies are disabled
            get_or_create_cart_id(request)
            return redirect_to_url(eventreverse(request.event, 'presale:event.seatingplan', kwargs=kwargs) + '?' + urlencode({
                **utm_params,
                'require_cookie': 'true',
                'cart_id': request.GET.get('take_cart_id'),
            }))
        elif request.GET.get('iframe', '') == '1' and len(self.request.GET.get('widget_data', '{}')) > 3:
            # We've been passed data from a widget, we need to create a cart session to store it.
            get_or_create_cart_id(request)

        if request.event.has_subevents:
            if 'subevent' in kwargs:
                self.subevent = request.event.subevents.using(settings.DATABASE_REPLICA).filter(pk=kwargs['subevent'], active=True).first()
                if not self.subevent or not self.subevent.seating_plan:
                    raise Http404()
                return super().get(request, *args, **kwargs)
            else:
                raise Http404()
        else:
            if 'subevent' in kwargs or not request.event.seating_plan:
                raise Http404()
            else:
                return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        _html_head = []
        for receiver, response in seatingframe_html_head.send(self.request.event, request=self.request):
            _html_head.append(response)
        context['seatingframe_html_head'] = "".join(_html_head)
        context['subevent'] = self.subevent
        context['cart_redirect'] = eventreverse(self.request.event, 'presale:event.checkout.start',
                                                kwargs={'cart_namespace': kwargs.get('cart_namespace') or ''})
        if context['cart_redirect'].startswith('https:'):
            context['cart_redirect'] = '/' + context['cart_redirect'].split('/', 3)[3]

        utm_params = {k: v for k, v in self.request.GET.items() if k.startswith("utm_")}
        if utm_params:
            context['cart_redirect'] += '?' + urlencode(utm_params)

        v = self.request.GET.get('voucher')
        if v:
            v = v.strip()
            try:
                voucher = self.request.event.vouchers.get(code__iexact=v)
                if voucher.redeemed >= voucher.max_usages or voucher.valid_until is not None \
                        and voucher.valid_until < now() or voucher.item is not None \
                        and voucher.item.is_available() is False:
                    voucher = None
            except Voucher.DoesNotExist:
                voucher = None
        else:
            voucher = None
        context['voucher'] = voucher

        return context


class EventIcalDownload(EventViewMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.request.event:
            raise Http404(_('Unknown event code or not authorized to access this event.'))

        subevent = None
        if request.event.has_subevents:
            if 'subevent' in kwargs:
                subevent = get_object_or_404(SubEvent, event=request.event, pk=kwargs['subevent'], active=True)
            else:
                raise Http404(pgettext_lazy('subevent', 'No date selected.'))
        else:
            if 'subevent' in kwargs:
                raise Http404(pgettext_lazy('subevent', 'Unknown date selected.'))

        event = self.request.event
        cal = get_public_ical([subevent or event])

        resp = HttpResponse(cal.serialize(), content_type='text/calendar')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}.ics"'.format(
            event.organizer.slug, event.slug, subevent.pk if subevent else '0',
        )
        if event.settings.meta_noindex:
            resp['X-Robots-Tag'] = 'noindex'
        return resp


class EventAuth(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        s = SessionStore(request.POST.get('session'))

        try:
            data = s.load()
        except:
            raise PermissionDenied(_('Please go back and try again.'))

        parent = data.get('pretix_event_access_{}'.format(request.event.pk))

        sparent = SessionStore(parent)
        try:
            parentdata = sparent.load()
        except:
            raise PermissionDenied(_('Please go back and try again.'))
        else:
            if 'child_session_{}'.format(request.event.pk) not in parentdata:
                raise PermissionDenied(_('Please go back and try again.'))

        request.session['pretix_event_access_{}'.format(request.event.pk)] = parent

        if "next" in self.request.GET and url_has_allowed_host_and_scheme(
                url=self.request.GET.get("next"), allowed_hosts=request.host, require_https=True):
            return redirect_to_url(self.request.GET.get('next'))
        else:
            return redirect_to_url(eventreverse(request.event, 'presale:event.index'))


class TimemachineForm(forms.Form):
    now_dt = forms.SplitDateTimeField(
        label=_('Fake date time'),
        widget=SplitDateTimePickerWidget(),
        initial=lambda: now().astimezone(get_current_timezone()),
    )


class EventTimeMachine(EventViewMixin, TemplateView):
    template_name = 'pretixpresale/event/timemachine.html'

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if not has_time_machine_permission(request, request.event):
            raise PermissionDenied(_('You are not allowed to access time machine mode.'))
        if not request.event.testmode:
            raise PermissionDenied(_('This feature is only available in test mode.'))
        self.timemachine_form = TimemachineForm(
            data=request.method == 'POST' and request.POST or None,
            initial=(
                {'now_dt': parser.parse(request.session.get(f'timemachine_now_dt:{request.event.pk}', None))}
                if request.session.get(f'timemachine_now_dt:{request.event.pk}', None) else {}
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['timemachine_form'] = self.timemachine_form
        return ctx

    def post(self, request, *args, **kwargs):
        if request.POST.get("timemachine_disable"):
            del request.session[f'timemachine_now_dt:{request.event.pk}']
            messages.success(self.request, _('Time machine disabled!'))
            return redirect(self.get_success_url())
        elif self.timemachine_form.is_valid():
            request.session[f'timemachine_now_dt:{request.event.pk}'] = str(self.timemachine_form.cleaned_data['now_dt'])
            return redirect(eventreverse(request.event, "presale:event.index"))
        else:
            return self.get(request)

    def get_success_url(self) -> str:
        return eventreverse(self.request.event, 'presale:event.timemachine')
