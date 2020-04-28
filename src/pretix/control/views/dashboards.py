from datetime import timedelta
from decimal import Decimal

import pytz
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Count, Exists, IntegerField, Max, Min, OuterRef, Prefetch, Q, Subquery,
    Sum,
)
from django.db.models.functions import Coalesce, Greatest
from django.dispatch import receiver
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import formats
from django.utils.formats import date_format
from django.utils.html import escape
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext, ungettext

from pretix.base.decimal import round_decimal
from pretix.base.models import (
    Item, ItemVariation, Order, OrderPosition, OrderRefund, RequiredAction,
    SubEvent, Voucher, WaitingListEntry,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.timeline import timeline_for_event
from pretix.control.forms.event import CommentForm
from pretix.control.signals import (
    event_dashboard_widgets, user_dashboard_widgets,
)
from pretix.helpers.daterange import daterange

from ...base.models.orders import CancellationRequest
from ..logdisplay import OVERVIEW_BANLIST

NUM_WIDGET = '<div class="numwidget"><span class="num">{num}</span><span class="text">{text}</span></div>'


@receiver(signal=event_dashboard_widgets)
def base_widgets(sender, subevent=None, lazy=False, **kwargs):
    if not lazy:
        prodc = Item.objects.filter(
            event=sender, active=True,
        ).filter(
            (Q(available_until__isnull=True) | Q(available_until__gte=now())) &
            (Q(available_from__isnull=True) | Q(available_from__lte=now()))
        ).count()

        if subevent:
            opqs = OrderPosition.objects.filter(subevent=subevent)
        else:
            opqs = OrderPosition.objects

        tickc = opqs.filter(
            order__event=sender, item__admission=True,
            order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING),
        ).count()

        paidc = opqs.filter(
            order__event=sender, item__admission=True,
            order__status=Order.STATUS_PAID,
        ).count()

        if subevent:
            rev = opqs.filter(
                order__event=sender, order__status=Order.STATUS_PAID
            ).aggregate(
                sum=Sum('price')
            )['sum'] or Decimal('0.00')
        else:
            rev = Order.objects.filter(
                event=sender,
                status=Order.STATUS_PAID
            ).aggregate(sum=Sum('total'))['sum'] or Decimal('0.00')

    return [
        {
            'content': None if lazy else NUM_WIDGET.format(num=tickc, text=_('Attendees (ordered)')),
            'lazy': 'attendees-ordered',
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        },
        {
            'content': None if lazy else NUM_WIDGET.format(num=paidc, text=_('Attendees (paid)')),
            'lazy': 'attendees-paid',
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        },
        {
            'content': None if lazy else NUM_WIDGET.format(
                num=formats.localize(round_decimal(rev, sender.currency)), text=_('Total revenue ({currency})').format(currency=sender.currency)),
            'lazy': 'total-revenue',
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            }) + ('?subevent={}'.format(subevent.pk) if subevent else '')
        },
        {
            'content': None if lazy else NUM_WIDGET.format(num=prodc, text=_('Active products')),
            'lazy': 'active-products',
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.items', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
    ]


@receiver(signal=event_dashboard_widgets)
def waitinglist_widgets(sender, subevent=None, lazy=False, **kwargs):
    widgets = []

    wles = WaitingListEntry.objects.filter(event=sender, subevent=subevent, voucher__isnull=True)
    if wles.exists():
        if not lazy:
            quota_cache = {}
            happy = 0
            tuples = wles.values('item', 'variation').order_by().annotate(cnt=Count('id'))

            items = {
                i.pk: i for i in sender.items.filter(id__in=[t['item'] for t in tuples]).prefetch_related(
                    Prefetch('quotas',
                             to_attr='_subevent_quotas',
                             queryset=sender.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent)),
                )
            }
            vars = {
                i.pk: i for i in ItemVariation.objects.filter(
                    item__event=sender, id__in=[t['variation'] for t in tuples if t['variation']]
                ).prefetch_related(
                    Prefetch('quotas',
                             to_attr='_subevent_quotas',
                             queryset=sender.quotas.using(settings.DATABASE_REPLICA).filter(subevent=subevent)),
                )
            }

            for wlt in tuples:
                item = items.get(wlt['item'])
                variation = vars.get(wlt['variation'])
                if not item:
                    continue
                quotas = (
                    variation._get_quotas(subevent=subevent)
                    if variation
                    else item._get_quotas(subevent=subevent)
                )
                row = (
                    variation.check_quotas(subevent=subevent, count_waitinglist=False, _cache=quota_cache)
                    if variation
                    else item.check_quotas(subevent=subevent, count_waitinglist=False, _cache=quota_cache)
                )
                if row[1] is None:
                    happy += 1
                elif row[1] > 0:
                    happy += 1
                    for q in quotas:
                        if q.size is not None:
                            quota_cache[q.pk] = (quota_cache[q.pk][0], quota_cache[q.pk][1] - 1)

        widgets.append({
            'content': None if lazy else NUM_WIDGET.format(
                num=str(happy), text=_('available to give to people on waiting list')
            ),
            'lazy': 'waitinglist-avail',
            'priority': 50,
            'url': reverse('control:event.orders.waitinglist', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug,
            })
        })
        widgets.append({
            'content': None if lazy else NUM_WIDGET.format(num=str(wles.count()), text=_('total waiting list length')),
            'lazy': 'waitinglist-length',
            'display_size': 'small',
            'priority': 50,
            'url': reverse('control:event.orders.waitinglist', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug,
            })
        })

    return widgets


@receiver(signal=event_dashboard_widgets)
def quota_widgets(sender, subevent=None, lazy=False, **kwargs):
    widgets = []
    quotas = sender.quotas.filter(subevent=subevent)

    quotas_to_compute = [
        q for q in quotas
        if not q.cache_is_hot(now() + timedelta(seconds=5))
    ]
    qa = QuotaAvailability()
    if quotas_to_compute:
        qa.queue(*quotas_to_compute)
        qa.compute()

    for q in quotas:
        if not lazy:
            status, left = qa.results[q] if q in qa.results else q.availability(allow_cache=True)
        widgets.append({
            'content': None if lazy else NUM_WIDGET.format(
                num='{}/{}'.format(left, q.size) if q.size is not None else '\u221e',
                text=_('{quota} left').format(quota=escape(q.name))
            ),
            'lazy': 'quota-{}'.format(q.pk),
            'display_size': 'small',
            'priority': 50,
            'url': reverse('control:event.items.quotas.show', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug,
                'quota': q.id
            })
        })
    return widgets


@receiver(signal=event_dashboard_widgets)
def shop_state_widget(sender, **kwargs):
    return [{
        'display_size': 'small',
        'priority': 1000,
        'content': '<div class="shopstate">{t1}<br><span class="{cls}"><span class="fa {icon}"></span> {state}</span>{t2}</div>'.format(
            t1=_('Your ticket shop is'), t2=_('Click here to change'),
            state=_('live') if sender.live and not sender.testmode else (
                _('live and in test mode') if sender.live else (
                    _('not yet public') if not sender.testmode else (
                        _('in private test mode')
                    )
                )
            ),
            icon='fa-check-circle' if sender.live and not sender.testmode else (
                'fa-warning' if sender.live else (
                    'fa-times-circle' if not sender.testmode else (
                        'fa-times-circle'
                    )
                )
            ),
            cls='live' if sender.live else 'off'
        ),
        'url': reverse('control:event.live', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug
        })
    }]


@receiver(signal=event_dashboard_widgets)
def checkin_widget(sender, subevent=None, lazy=False, **kwargs):
    widgets = []
    qs = sender.checkin_lists.filter(subevent=subevent)
    for cl in qs:
        widgets.append({
            'content': None if lazy else NUM_WIDGET.format(
                num='{}/{}'.format(cl.checkin_count, cl.position_count),
                text=_('Checked in – {list}').format(list=escape(cl.name))
            ),
            'lazy': 'checkin-{}'.format(cl.pk),
            'display_size': 'small',
            'priority': 50,
            'url': reverse('control:event.orders.checkinlists.show', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug,
                'list': cl.pk
            })
        })
    return widgets


@receiver(signal=event_dashboard_widgets)
def welcome_wizard_widget(sender, **kwargs):
    template = get_template('pretixcontrol/event/dashboard_widget_welcome.html')
    ctx = {
        'title': _('Welcome to pretix!')
    }
    kwargs = {'event': sender.slug, 'organizer': sender.organizer.slug}

    if not sender.items.exists():
        ctx.update({
            'subtitle': _('Get started with our setup tool'),
            'text': _('To start selling tickets, you need to create products or quotas. The fastest way to create '
                      'this is to use our setup tool.'),
            'button_text': _('Set up event'),
            'button_url': reverse('control:event.quick', kwargs=kwargs)
        })
    else:
        return []
    return [{
        'display_size': 'full',
        'priority': 2000,
        'content': template.render(ctx)
    }]


def event_index(request, organizer, event):
    subevent = None
    if request.GET.get("subevent", "") != "" and request.event.has_subevents:
        i = request.GET.get("subevent", "")
        try:
            subevent = request.event.subevents.get(pk=i)
        except SubEvent.DoesNotExist:
            pass

    widgets = []
    for r, result in event_dashboard_widgets.send(sender=request.event, subevent=subevent, lazy=True):
        widgets.extend(result)

    can_change_orders = request.user.has_event_permission(request.organizer, request.event, 'can_change_orders',
                                                          request=request)
    qs = request.event.logentry_set.all().select_related('user', 'content_type', 'api_token', 'oauth_application',
                                                         'device').order_by('-datetime')
    qs = qs.exclude(action_type__in=OVERVIEW_BANLIST)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_view_orders', request=request):
        qs = qs.exclude(content_type=ContentType.objects.get_for_model(Order))
    if not request.user.has_event_permission(request.organizer, request.event, 'can_view_vouchers', request=request):
        qs = qs.exclude(content_type=ContentType.objects.get_for_model(Voucher))

    a_qs = request.event.requiredaction_set.filter(done=False)

    ctx = {
        'widgets': rearrange(widgets),
        'logs': qs[:5],
        'subevent': subevent,
        'actions': a_qs[:5] if can_change_orders else [],
        'comment_form': CommentForm(initial={'comment': request.event.comment})
    }

    ctx['has_overpaid_orders'] = Order.annotate_overpayments(request.event.orders).filter(
        Q(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=0))
        | Q(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=0))
    ).exists()
    ctx['has_pending_orders_with_full_payment'] = Order.annotate_overpayments(request.event.orders).filter(
        Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0) & Q(require_approval=False)
    ).exists()
    ctx['has_pending_refunds'] = OrderRefund.objects.filter(
        order__event=request.event,
        state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_EXTERNAL)
    ).exists()
    ctx['has_pending_approvals'] = request.event.orders.filter(
        status=Order.STATUS_PENDING,
        require_approval=True
    ).exists()
    ctx['has_cancellation_requests'] = CancellationRequest.objects.filter(
        order__event=request.event
    ).exists()

    for a in ctx['actions']:
        a.display = a.display(request)

    ctx['timeline'] = [
        {
            'date': t.datetime.astimezone(request.event.timezone).date(),
            'entry': t,
            'time': t.datetime.astimezone(request.event.timezone)
        }
        for t in timeline_for_event(request.event, subevent)
    ]
    ctx['today'] = now().astimezone(request.event.timezone).date()
    ctx['nearly_now'] = now().astimezone(request.event.timezone) - timedelta(seconds=20)
    resp = render(request, 'pretixcontrol/event/index.html', ctx)
    # resp['Content-Security-Policy'] = "style-src 'unsafe-inline'"
    return resp


def event_index_widgets_lazy(request, organizer, event):
    subevent = None
    if request.GET.get("subevent", "") != "" and request.event.has_subevents:
        i = request.GET.get("subevent", "")
        try:
            subevent = request.event.subevents.get(pk=i)
        except SubEvent.DoesNotExist:
            pass

    widgets = []
    for r, result in event_dashboard_widgets.send(sender=request.event, subevent=subevent, lazy=False):
        widgets.extend(result)

    return JsonResponse({'widgets': widgets})


def annotated_event_query(request, lazy=False):
    active_orders = Order.objects.filter(
        event=OuterRef('pk'),
        status__in=[Order.STATUS_PENDING, Order.STATUS_PAID]
    ).order_by().values('event').annotate(
        c=Count('*')
    ).values(
        'c'
    )

    required_actions = RequiredAction.objects.filter(
        event=OuterRef('pk'),
        done=False
    )
    qs = request.user.get_events_with_any_permission(request)
    if not lazy:
        qs = qs.annotate(
            order_count=Subquery(active_orders, output_field=IntegerField()),
            has_ra=Exists(required_actions)
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
            Q(organizer_id__in=user.teams.filter(all_events=True, can_view_orders=True).values_list('organizer', flat=True))
            | Q(id__in=user.teams.filter(can_view_orders=True).values_list('limit_events__id', flat=True))
        ).values_list('id', flat=True))

    tpl = """
        <a href="{url}" class="event">
            <div class="name">{event}</div>
            <div class="daterange">{daterange}</div>
            <div class="times">{times}</div>
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
            tz = pytz.timezone(tzname)
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

            if event.has_ra:
                status = ('danger', _('Action required'))
            elif not event.live:
                status = ('warning', _('Shop disabled'))
            elif event.presale_has_ended:
                status = ('default', _('Sale over'))
            elif not event.presale_is_running:
                status = ('default', _('Soon'))
            else:
                status = ('success', _('On sale'))

        widgets.append({
            'content': tpl.format(
                event=escape(event.name),
                times=_('Event series') if event.has_subevents else (
                    ((date_format(event.date_admission.astimezone(tz), 'TIME_FORMAT') + ' / ')
                     if event.date_admission and event.date_admission != event.date_from else '')
                    + (date_format(event.date_from.astimezone(tz), 'TIME_FORMAT') if event.date_from else '')
                ) + (
                    ' <span class="fa fa-globe text-muted" data-toggle="tooltip" title="{}"></span>'.format(tzname)
                    if tzname != request.timezone and not event.has_subevents else ''
                ),
                url=reverse('control:event.index', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug
                }),
                orders=(
                    '<a href="{orders_url}" class="orders">{orders_text}</a>'.format(
                        orders_url=reverse('control:event.orders', kwargs={
                            'event': event.slug,
                            'organizer': event.organizer.slug
                        }),
                        orders_text=ungettext('{num} order', '{num} orders', event.order_count or 0).format(
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
    return JsonResponse({'widgets': widgets})


def user_index(request):
    widgets = []
    for r, result in user_dashboard_widgets.send(request, user=request.user):
        widgets.extend(result)

    ctx = {
        'widgets': rearrange(widgets),
        'can_create_event': request.user.teams.filter(can_create_events=True).exists(),
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
