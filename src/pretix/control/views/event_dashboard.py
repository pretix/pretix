from decimal import Decimal

from django.core.urlresolvers import reverse
from django.db.models import Sum
from django.dispatch import receiver
from django.shortcuts import render
from django.utils import formats
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item, Order, OrderPosition
from pretix.control.signals import event_dashboard_widgets

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


def index(request, organizer, event):
    widgets = []
    for r, result in event_dashboard_widgets.send(sender=request.event):
        widgets.extend(result)
    ctx = {
        'widgets': rearrange(widgets),
    }
    return render(request, 'pretixcontrol/event/index.html', ctx)


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
