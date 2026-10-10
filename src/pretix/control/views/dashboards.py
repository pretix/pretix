#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
# This file contains Apache-licensed contributions copyrighted by: Sohalt, Tobias Kunze, jasonwaiting@live.hk
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Count, IntegerField, Max, Min, OuterRef, Q, Subquery,
)
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import (
    conditional_escape, escape, format_html, format_html_join,
)
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, ngettext, pgettext

from pretix.base.models import (
    Item, ItemCategory, Order, OrderRefund, Question, Quota, Voucher,
    WaitingListEntry,
)
from pretix.base.timeline import timeline_for_event
from pretix.control.signals import (
    event_dashboard_statistics, user_dashboard_widgets,
)
from pretix.helpers.daterange import daterange

from ...base.models.orders import CancellationRequest
from ...base.models.organizer import TeamQuerySet
from ..logdisplay import OVERVIEW_BANLIST
from .utils import prepare_quotas_for_boxes


def event_index_waiting_lazy(request, organizer, event):
    wles = WaitingListEntry.objects.filter(event=request.event, voucher__isnull=True)
    return render(
        request,
        'pretixcontrol/event/dashboard_partial_waiting.html',
        {
            'count': wles.count,
        }
    )


def build_json_response(widgets):
    for widget in widgets:
        widget['content'] = conditional_escape(widget['content'])
    return JsonResponse({'widgets': widgets})


def event_index(request, organizer, event):
    can_view_orders = request.user.has_event_permission(
        request.organizer,
        request.event,
        'event.orders:read',
        request=request
    )

    stats = []
    if can_view_orders:
        for r, result in event_dashboard_statistics.send(sender=request.event, request=request):
            stats.append(result)

    ctx = {
        'stats': format_html_join("", "{}", [(s,) for s in stats]),
    }

    if not request.event.has_subevents:
        ctx['timeline'] = [
            {
                'date': t.datetime.astimezone(request.event.timezone).date(),
                'entry': t,
                'time': t.datetime.astimezone(request.event.timezone)
            }
            for t in timeline_for_event(request.event, None)
        ]
    ctx['today'] = now().astimezone(request.event.timezone).date()
    ctx['nearly_now'] = now().astimezone(request.event.timezone) - timedelta(seconds=20)
    ctx['has_checkin_widgets'] = not request.event.has_subevents or request.event.checkin_lists.filter(subevent=None).exists()
    resp = render(request, 'pretixcontrol/event/index.html', ctx)
    return resp


def event_index_warnings_lazy(request, organizer, event):
    can_view_orders = request.user.has_event_permission(request.organizer, request.event, 'event.orders:read',
                                                        request=request)
    can_change_event_settings = request.user.has_event_permission(request.organizer, request.event,
                                                                  'event.settings.general:write', request=request)
    ctx = {}
    ctx['has_overpaid_orders'] = can_view_orders and Order.annotate_overpayments(request.event.orders).filter(
        Q(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=0))
        | Q(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=0))
    ).exists()
    ctx['has_pending_orders_with_full_payment'] = can_view_orders and Order.annotate_overpayments(request.event.orders).filter(
        Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0) & Q(require_approval=False)
    ).exists()
    ctx['has_pending_refunds'] = can_view_orders and OrderRefund.objects.filter(
        order__event=request.event,
        state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_EXTERNAL)
    ).exists()
    ctx['has_pending_approvals'] = can_view_orders and request.event.orders.filter(
        status=Order.STATUS_PENDING,
        require_approval=True
    ).exists()
    ctx['has_cancellation_requests'] = can_view_orders and CancellationRequest.objects.filter(
        order__event=request.event
    ).exists()
    ctx['has_sync_problems'] = can_change_event_settings and request.event.queued_sync_jobs.filter(
        Q(need_manual_retry__isnull=False)
        | Q(failed_attempts__gt=0)
    ).exists()

    return render(
        request,
        'pretixcontrol/event/dashboard_partial_warnings.html',
        ctx
    )


def event_index_quotas_lazy(request, organizer, event):
    if request.event.has_subevents:
        raise Http404()

    quotas = request.event.quotas.filter(subevent=None)[:10]
    prepare_quotas_for_boxes(quotas)
    return render(
        request,
        'pretixcontrol/event/dashboard_partial_quotas.html',
        {
            'quotas': quotas,
        }
    )


def event_index_checkin_lazy(request, organizer, event):
    lists = request.event.checkin_lists.filter(subevent=None)[:10]
    return render(
        request,
        'pretixcontrol/event/dashboard_partial_checkin.html',
        {
            'lists': lists,
        }
    )


def event_index_log_lazy(request, organizer, event):
    qs = request.event.logentry_set.all().select_related('user', 'content_type', 'api_token', 'oauth_application',
                                                         'device').order_by('-datetime')
    qs = qs.exclude(action_type__in=OVERVIEW_BANLIST)

    can_view_orders = request.user.has_event_permission(request.organizer, request.event, 'event.orders:read',
                                                        request=request)
    can_change_event_settings = request.user.has_event_permission(request.organizer, request.event,
                                                                  'event.settings.general:write', request=request)
    can_view_vouchers = request.user.has_event_permission(request.organizer, request.event, 'event.vouchers:read',
                                                          request=request)

    if not can_view_orders:
        qs = qs.exclude(content_type=ContentType.objects.get_for_model(Order))
    if not can_view_vouchers:
        qs = qs.exclude(content_type=ContentType.objects.get_for_model(Voucher))
    if not can_change_event_settings:
        allowed_types = [
            ContentType.objects.get_for_model(Voucher),
            ContentType.objects.get_for_model(Order)
        ]
        if request.user.has_event_permission(request.organizer, request.event, 'event.items:write', request=request):
            allowed_types += [
                ContentType.objects.get_for_model(Item),
                ContentType.objects.get_for_model(ItemCategory),
                ContentType.objects.get_for_model(Quota),
                ContentType.objects.get_for_model(Question),
            ]
        qs = qs.filter(content_type__in=allowed_types)

    return render(
        request,
        'pretixcontrol/event/dashboard_partial_logs.html',
        {
            'logs': qs[:5]
        }
    )


def annotated_event_query(request, lazy=False):
    active_orders = Order.objects.filter(
        event=OuterRef('pk'),
        status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
    ).order_by().values('event').annotate(
        c=Count('*')
    ).values(
        'c'
    )

    qs = request.user.get_events_with_any_permission(request)
    if not lazy:
        qs = qs.annotate(
            order_count=Subquery(active_orders, output_field=IntegerField()),
        )
    qs = qs.annotate(
        min_from=Min('subevents__date_from'),
        max_from=Max('subevents__date_from'),
        max_to=Max('subevents__date_to'),
        max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from')),
    ).annotate(
        order_to=Coalesce('max_fromto', 'max_to', 'max_from', 'date_to', 'date_from'),
    )
    return qs


def widgets_for_event_qs(request, qs, user, nmax, lazy=False):
    widgets = []

    # Get set of events where we have the permission to show the # of orders
    if not lazy:
        events_with_orders = set(qs.filter(
            Q(organizer_id__in=user.teams.filter(
                TeamQuerySet.event_permission_q("event.orders:read"),
                all_events=True,
            ).values_list('organizer', flat=True))
            | Q(id__in=user.teams.filter(
                TeamQuerySet.event_permission_q("event.orders:read"),
            ).values_list('limit_events__id', flat=True))
        ).values_list('id', flat=True))

    tpl = """
        <a href="{url}" class="event">
            <div class="name">{event}</div>
            <div class="daterange">{daterange}</div>
            <div class="times">{times}{timezone}</div>
        </a>
        <div class="bottomrow">
            {orders}
            <a href="{url}" class="status-{statusclass}">
                {status}
            </a>
        </div>
    """

    if lazy:
        events = qs[:nmax]
    else:
        events = qs.prefetch_related(
            '_settings_objects', 'organizer___settings_objects'
        ).select_related('organizer')[:nmax]
    for event in events:
        if not lazy:
            tzname = event.cache.get_or_set('timezone', lambda: event.settings.timezone)
            tz = ZoneInfo(tzname)
            if event.has_subevents:
                if event.min_from is None:
                    dr = pgettext("subevent", "No dates")
                else:
                    dr = daterange(
                        (event.min_from).astimezone(tz),
                        (event.max_fromto or event.max_to or event.max_from).astimezone(tz)
                    )
            else:
                if event.date_to:
                    dr = daterange(event.date_from.astimezone(tz), event.date_to.astimezone(tz))
                else:
                    dr = date_format(event.date_from.astimezone(tz), "DATE_FORMAT")

            if not event.live:
                status = ('warning', _('Shop disabled'))
            elif event.presale_has_ended:
                status = ('default', _('Sale over'))
            elif not event.presale_is_running:
                status = ('default', _('Soon'))
            else:
                status = ('success', _('On sale'))

        widgets.append({
            'content': format_html(
                tpl,
                event=escape(event.name),
                times=_('Event series') if event.has_subevents else (
                    ((date_format(event.date_admission.astimezone(tz), 'TIME_FORMAT') + ' / ')
                     if event.date_admission and event.date_admission != event.date_from else '')
                    + (date_format(event.date_from.astimezone(tz), 'TIME_FORMAT') if event.date_from else '')
                ),
                timezone=(
                    format_html(' <span class="fa fa-globe text-muted" data-toggle="tooltip" title="{}"></span>', tzname)
                    if tzname != request.timezone and not event.has_subevents else ''
                ),
                url=reverse('control:event.index', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug
                }),
                orders=(
                    format_html(
                        '<a href="{orders_url}" class="orders">{orders_text}</a>',
                        orders_url=reverse('control:event.orders', kwargs={
                            'event': event.slug,
                            'organizer': event.organizer.slug
                        }),
                        orders_text=ngettext('{num} order', '{num} orders', event.order_count or 0).format(
                            num=event.order_count or 0
                        )
                    ) if user.has_active_staff_session(request.session.session_key) or event.pk in events_with_orders else ''
                ),
                daterange=dr,
                status=status[1],
                statusclass=status[0],
            ) if not lazy else '',
            'display_size': 'small',
            'lazy': 'event-{}'.format(event.pk),
            'priority': 100,
            'container_class': 'widget-container widget-container-event',
        })
        """
            {% if not e.live %}
                <span class="label label-danger">{% trans "Shop disabled" %}</span>
            {% elif e.presale_has_ended %}
                <span class="label label-warning">{% trans "Presale over" %}</span>
            {% elif not e.presale_is_running %}
                <span class="label label-warning">{% trans "Presale not started" %}</span>
            {% else %}
                <span class="label label-success">{% trans "On sale" %}</span>
            {% endif %}
        """
    return widgets


def user_index_widgets_lazy(request):
    widgets = []
    widgets += widgets_for_event_qs(
        request,
        annotated_event_query(request).filter(
            Q(has_subevents=False) &
            Q(
                Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                | Q(Q(date_to__isnull=False) & Q(date_to__gte=now()))
            )
        ).order_by('date_from', 'order_to', 'pk'),
        request.user,
        7
    )
    widgets += widgets_for_event_qs(
        request,
        annotated_event_query(request).filter(
            Q(has_subevents=False) &
            Q(
                Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
                | Q(Q(date_to__isnull=False) & Q(date_to__lt=now()))
            )
        ).order_by('-order_to', 'pk'),
        request.user,
        8
    )
    widgets += widgets_for_event_qs(
        request,
        annotated_event_query(request).filter(
            has_subevents=True
        ).order_by('-order_to', 'pk'),
        request.user,
        8
    )
    return build_json_response(widgets)


def user_index(request):
    widgets = []
    for r, result in user_dashboard_widgets.send(request, user=request.user):
        widgets.extend(result)

    ctx = {
        'widgets': rearrange(widgets),
        'can_create_event': request.user.teams.with_organizer_permission("organizer.events:create").exists() or request.user.is_staff,
        'upcoming': widgets_for_event_qs(
            request,
            annotated_event_query(request, lazy=True).filter(
                Q(has_subevents=False) &
                Q(
                    Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                    | Q(Q(date_to__isnull=False) & Q(date_to__gte=now()))
                )
            ).order_by('date_from', 'order_to', 'pk'),
            request.user,
            7,
            lazy=True
        ),
        'past': widgets_for_event_qs(
            request,
            annotated_event_query(request, lazy=True).filter(
                Q(has_subevents=False) &
                Q(
                    Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
                    | Q(Q(date_to__isnull=False) & Q(date_to__lt=now()))
                )
            ).order_by('-order_to', 'pk'),
            request.user,
            8,
            lazy=True
        ),
        'series': widgets_for_event_qs(
            request,
            annotated_event_query(request, lazy=True).filter(
                has_subevents=True
            ).order_by('-order_to', 'pk'),
            request.user,
            8,
            lazy=True
        ),
    }
    return render(request, 'pretixcontrol/dashboard.html', ctx)


def rearrange(widgets: list):
    """
    Sort widget boxes according to priority.
    """
    mapping = {
        'small': 1,
        'big': 2,
        'full': 3,
    }

    def sort_key(element):
        return (
            element.get('priority', 1),
            mapping.get(element.get('display_size', 'small'), 1),
        )

    return sorted(widgets, key=sort_key, reverse=True)
