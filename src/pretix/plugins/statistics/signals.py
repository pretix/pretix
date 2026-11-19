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
from decimal import Decimal

from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Sum
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from pretix.base.decimal import round_decimal
from pretix.base.models import Order, OrderPosition
from pretix.base.signals import order_paid, order_placed
from pretix.base.templatetags.money import money_filter
from pretix.control.signals import event_dashboard_statistics, nav_event


@receiver(nav_event, dispatch_uid="statistics_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'event.orders:read', request=request):
        return []
    return [
        {
            'label': _('Statistics'),
            'url': reverse('plugins:statistics:index', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'parent': reverse('control:event.orders', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:statistics'),
            'icon': 'bar-chart',
        }
    ]


def clear_cache(sender, *args, **kwargs):
    cache = sender.cache
    cache.delete('statistics_obd_data')
    cache.delete('statistics_obp_data')
    cache.delete('statistics_rev_data')


order_placed.connect(clear_cache)
order_paid.connect(clear_cache)


@receiver(event_dashboard_statistics, dispatch_uid="statistics_event_dashboard_state")
def event_dashboard_stats_receivers(sender, request, **kwargs):
    if len(event_dashboard_statistics.receivers) > 1:
        # Only render this as a fallback if no other plugins exist
        return ""

    opqs = OrderPosition.objects
    tickc = opqs.filter(
        order__event=sender, item__admission=True,
        order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING),
    ).count()
    paidc = opqs.filter(
        order__event=sender, item__admission=True,
        order__status=Order.STATUS_PAID,
    ).count()
    rev = Order.objects.filter(
        event=sender,
        status=Order.STATUS_PAID
    ).aggregate(sum=Sum('total'))['sum'] or Decimal('0.00')
    num_widget = '<div class="numwidget"><span class="num">{num}</span><span class="text">{text}</span></div>'

    widgets = [
        {
            'content': format_html(num_widget, num=intcomma(tickc), text=_('Attendees (ordered)')),
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': format_html(num_widget, num=intcomma(paidc), text=_('Attendees (paid)')),
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': format_html(
                num_widget,
                num=money_filter(round_decimal(rev, sender.currency), sender.currency, hide_currency=True),
                text=_('Total revenue ({currency})').format(currency=sender.currency)
            ),
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
    ]
    template = get_template('pretixplugins/statistics/dashboard.html')
    ctx = {'request': request, 'widgets': widgets}
    return template.render(ctx)
