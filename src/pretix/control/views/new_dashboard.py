import json
import datetime
from decimal import Decimal

import dateutil
from django.db.models import DateTimeField, Max, OuterRef, Q, Subquery, Sum
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from pretix.base.channels import get_all_sales_channels
from pretix.base.decimal import round_decimal
from pretix.base.models import SubEvent
from pretix.base.models.orders import (
    CancellationRequest, Order, OrderPayment, OrderPosition, OrderRefund,
)
from pretix.base.timeline import timeline_for_event
from pretix.control.forms.event import CommentForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import ChartContainingView

NUM_WIDGET = str('<div class="numwidget"><span class="num">{num}</span>'
                 '<span class="text">{text}</span>'
                 '<span class="text-add">{text_add}</span></div>')


class IndexView(EventPermissionRequiredMixin, ChartContainingView, TemplateView):
    template_name = 'pretixcontrol/event/new_index.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        subevent = None
        if self.request.GET.get("subevent", "") != "" and self.request.event.has_subevents:
            i = self.request.GET.get("subevent", "")
            try:
                subevent = self.request.event.subevents.get(pk=i)
            except SubEvent.DoesNotExist:
                pass

        can_view_orders = self.request.user.has_event_permission(self.request.organizer, self.request.event,
                                                                 'can_view_orders',
                                                                 request=self.request)
        can_change_event_settings = self.request.user.has_event_permission(self.request.organizer, self.request.event,
                                                                           'can_change_event_settings',
                                                                           request=self.request)

        ctx = {
            'subevent': subevent,
            'comment_form': CommentForm(initial={'comment': self.request.event.comment},
                                        readonly=not can_change_event_settings),
        }

        if subevent:
            opqs = OrderPosition.objects.filter(subevent=subevent)
        else:
            opqs = OrderPosition.objects

        ctx['shop_state'] = {
            'display_size': 'small',
            'priority': 1000,
            'content': '<span class="{cls}">{t1} {state} <span class="fa {icon}"></span></span>'.format(
                t1=_('Your ticket shop is'),
                state=_('live') if self.request.event.live and not self.request.event.testmode else (
                    _('live and in test mode') if self.request.event.live else (
                        _('not yet public') if not self.request.event.testmode else (
                            _('in private test mode')
                        )
                    )
                ),
                icon='fa-check-circle' if self.request.event.live and not self.request.event.testmode else (
                    'fa-warning' if self.request.event.live else (
                        'fa-times-circle' if not self.request.event.testmode else (
                            'fa-lock'
                        )
                    )
                ),
                cls='live' if self.request.event.live else 'off'
            ),
            'url': reverse('control:event.live', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            })
        }

        qs = self.request.event.checkin_lists.filter(subevent=subevent)
        sales_channels = get_all_sales_channels()
        for cl in qs:
            if cl.subevent:
                cl.subevent.event = self.request.event  # re-use same event object to make sure settings are cached
            cl.auto_checkin_sales_channels = [sales_channels[channel] for channel in cl.auto_checkin_sales_channels]
        ctx['checkinlists'] = qs

        tickc = opqs.filter(
            order__event=self.request.event, item__admission=True,
            order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING),
        ).count()
        ctx['attendees_ordered'] = {
            'content': NUM_WIDGET.format(num=f'{tickc} <span class="fa fa-users"></span>',
                                         text=_('Attendees (ordered)'),
                                         text_add=''),
            'priority': 100,
            'url': reverse('control:event.orders', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        }
        paidc = opqs.filter(
            order__event=self.request.event, item__admission=True,
            order__status=Order.STATUS_PAID,
        ).count()
        ctx['attendees_paid'] = {
            'content': NUM_WIDGET.format(num=f'{paidc} <span class="fa fa-money"></span>', text=_('Attendees (paid)'),
                                         text_add=''),
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        }
        ctx['attendees_paid_ordered'] = {
            'content': NUM_WIDGET.format(
                num=f'<span class="fa fa-user"></span> {tickc}',
                text=_('Attendees'),
                text_add=_(f'{paidc} paid, {tickc - paidc} pending')),
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        }

        if subevent:
            rev = opqs.filter(
                order__event=self.request.event, order__status=Order.STATUS_PAID
            ).aggregate(
                sum=Sum('price')
            )['sum'] or Decimal('0.00')
        else:
            rev = Order.objects.filter(
                event=self.request.event,
                status=Order.STATUS_PAID
            ).aggregate(sum=Sum('total'))['sum'] or Decimal('0.00')

        ctx['total_revenue'] = {
            'content': NUM_WIDGET.format(
                num=formats.localize(round_decimal(rev, self.request.event.currency)),
                text=_('Total revenue ({currency})').format(currency=self.request.event.currency),
                text_add=''),
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        }

        cache = self.request.event.cache
        ckey = str(subevent.pk) if subevent else 'all'
        tz = timezone.get_current_timezone()
        op_date = OrderPayment.objects.filter(
            order=OuterRef('order'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()
        p_date = OrderPayment.objects.filter(
            order=OuterRef('pk'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()
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
                rev = float(rev_by_day.get(d, 0))
                if True:  # rev != 0:
                    total += rev
                    data.append({
                        'date': d.strftime('%Y-%m-%d'),
                        'revenue': round(total, 2),
                    })
            ctx['rev_data'] = json.dumps(data)
            cache.set('statistics_rev_data' + ckey, ctx['rev_data'])
        # ctx = ctx | statistics.get_context_data(IndexView(request=request))

        ctx['has_overpaid_orders'] = can_view_orders and Order.annotate_overpayments(self.request.event.orders).filter(
            Q(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=0))
            | Q(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=0))
        ).exists()
        ctx['has_pending_orders_with_full_payment'] = can_view_orders and Order.annotate_overpayments(
            self.request.event.orders).filter(
            Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0) & Q(
                require_approval=False)
        ).exists()
        ctx['has_pending_refunds'] = can_view_orders and OrderRefund.objects.filter(
            order__event=self.request.event,
            state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_EXTERNAL)
        ).exists()
        ctx['has_pending_approvals'] = can_view_orders and self.request.event.orders.filter(
            status=Order.STATUS_PENDING,
            require_approval=True
        ).exists()
        ctx['has_cancellation_requests'] = can_view_orders and CancellationRequest.objects.filter(
            order__event=self.request.event
        ).exists()

        ctx['timeline'] = [
            {
                'date': t.datetime.astimezone(self.request.event.timezone).date(),
                'entry': t,
                'time': t.datetime.astimezone(self.request.event.timezone)
            }
            for t in timeline_for_event(self.request.event, subevent)
        ]
        ctx['today'] = now().astimezone(self.request.event.timezone).date()
        ctx['nearly_now'] = now().astimezone(self.request.event.timezone) - datetime.timedelta(seconds=20)
        # resp['Content-Security-Policy'] = "style-src 'unsafe-inline'"
        return ctx
