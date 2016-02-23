from decimal import Decimal

from django.core.urlresolvers import reverse
from django.db.models import Sum
from django.dispatch import receiver
from django.shortcuts import render
from django.utils import formats
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, Item, Order, OrderPosition
from pretix.control.signals import (
    event_dashboard_widgets, user_dashboard_widgets,
)

NUM_WIDGET = '<div class="numwidget"><span class="num">{num}</span><span class="text">{text}</span></div>'


@receiver(signal=event_dashboard_widgets)
def base_widgets(sender, **kwargs):
    prodc = Item.objects.filter(
        event=sender, active=True,
    ).count()

    tickc = OrderPosition.objects.filter(
        order__event=sender, item__admission=True
    ).count()

    paidc = OrderPosition.objects.filter(
        order__event=sender, item__admission=True,
        order__status=Order.STATUS_PAID,
    ).count()

    rev = Order.objects.filter(
        event=sender,
        status=Order.STATUS_PAID
    ).aggregate(sum=Sum('total'))['sum'] or Decimal('0.00')

    return [
        {
            'content': NUM_WIDGET.format(num=tickc, text=_('Attendees (ordered)')),
            'width': 3,
            'priority': 100,
            'url': reverse('control:event.orders', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(num=paidc, text=_('Attendees (paid)')),
            'width': 3,
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(
                num=formats.localize(rev), text=_('Total revenue ({currency})').format(currency=sender.currency)),
            'width': 3,
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(num=prodc, text=_('Active products')),
            'width': 3,
            'priority': 100,
            'url': reverse('control:event.items', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
    ]


@receiver(signal=event_dashboard_widgets)
def quota_widgets(sender, **kwargs):
    widgets = []
    for q in sender.quotas.all():
        status, left = q.availability()
        widgets.append({
            'content': NUM_WIDGET.format(num='{}/{}'.format(left, q.size) if q.size is not None else '\u221e',
                                         text=_('{quota} left').format(quota=q.name)),
            'width': 3,
            'priority': 50,
        })
    return widgets


@receiver(signal=event_dashboard_widgets)
def shop_state_widget(sender, **kwargs):
    return [{
        'width': 3,
        'priority': 1000,
        'content': '<div class="shopstate">{t1}<br><span class="{cls}"><span class="fa {icon}"></span> {state}</span>{t2}</div>'.format(
            t1=_('Your ticket shop is'), t2=_('Click here to change'),
            state=_('live') if sender.live else _('not yet public'),
            icon='fa-check-circle' if sender.live else 'fa-times-circle',
            cls='live' if sender.live else 'off'
        ),
        'url': reverse('control:event.live', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug
        })
    }]


def event_index(request, organizer, event):
    widgets = []
    for r, result in event_dashboard_widgets.send(sender=request.event):
        widgets.extend(result)
    ctx = {
        'widgets': rearrange(widgets),
    }
    return render(request, 'pretixcontrol/event/index.html', ctx)


@receiver(signal=user_dashboard_widgets)
def user_event_widgets(**kwargs):
    user = kwargs.pop('user')
    widgets = []
    events = Event.objects.filter(permitted__id__exact=user.pk).select_related("organizer").order_by('-date_from')
    for event in events:
        widgets.append({
            'content': '<div class="event">{event}<span class="from">{df}</span><span class="to">{dt}</span></div>'.format(
                event=event.name, df=date_format(event.date_from, 'SHORT_DATE_FORMAT'),
                dt=date_format(event.date_to, 'SHORT_DATE_FORMAT')
            ),
            'width': 3,
            'priority': 100,
            'url': reverse('control:event.index', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        })
    return widgets


@receiver(signal=user_dashboard_widgets)
def new_event_widgets(**kwargs):
    return [
        {
            'content': '<div class="newevent"><span class="fa fa-plus-circle"></span>{t}</div>'.format(
                t=_('Create a new event')
            ),
            'width': 3,
            'priority': 50,
            'url': reverse('control:events.add')
        }
    ]


def user_index(request):
    widgets = []
    for r, result in user_dashboard_widgets.send(request, user=request.user):
        widgets.extend(result)
    ctx = {
        'widgets': rearrange(widgets),
    }
    return render(request, 'pretixcontrol/dashboard.html', ctx)


def rearrange(widgets: list):
    """
    Small and stupid algorithm to arrange widget boxes without too many gaps while respecting
    priority. Doing this siginificantly better might be *really* hard.
    """
    oldlist = sorted(widgets, key=lambda w: -1 * w.get('priority', 1))
    newlist = []
    cpos = 0
    while len(oldlist) > 0:
        max_prio = max([w.get('priority', 1) for w in oldlist])
        try:
            best = max([w for w in oldlist if w.get('priority', 1) == max_prio and cpos + w.get('width', 3) <= 12],
                       key=lambda w: w.get('width', 3))
            cpos = (cpos + best.get('width', 3)) % 12
        except ValueError:  # max() arg is an empty sequence
            best = [w for w in oldlist if w.get('priority', 1) == max_prio][0]
            cpos = best.get('width', 3)
        oldlist.remove(best)
        newlist.append(best)

    return newlist
