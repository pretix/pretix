from decimal import Decimal

from django.core.urlresolvers import reverse
from django.db.models import Sum
from django.dispatch import receiver
from django.shortcuts import render
from django.template.loader import get_template
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
        order__event=sender, item__admission=True,
        order__status__in=(Order.STATUS_PAID, Order.STATUS_PENDING)
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
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(num=paidc, text=_('Attendees (paid)')),
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(
                num=formats.localize(rev), text=_('Total revenue ({currency})').format(currency=sender.currency)),
            'display_size': 'small',
            'priority': 100,
            'url': reverse('control:event.orders.overview', kwargs={
                'event': sender.slug,
                'organizer': sender.organizer.slug
            })
        },
        {
            'content': NUM_WIDGET.format(num=prodc, text=_('Active products')),
            'display_size': 'small',
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
            state=_('live') if sender.live else _('not yet public'),
            icon='fa-check-circle' if sender.live else 'fa-times-circle',
            cls='live' if sender.live else 'off'
        ),
        'url': reverse('control:event.live', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug
        })
    }]


@receiver(signal=event_dashboard_widgets)
def welcome_wizard_widget(sender, **kwargs):
    template = get_template('pretixcontrol/event/dashboard_widget_welcome.html')
    ctx = {
        'title': _('Welcome to pretix!')
    }
    kwargs = {'event': sender.slug, 'organizer': sender.organizer.slug}

    if not sender.items.exists():
        ctx.update({
            'subtitle': _('Get started by creating a product'),
            'text': _('The first thing you need for selling tickets to your event is one or more "products" your '
                      'participants can choose from. A product can be a ticket or anything else that you want to sell, '
                      'e.g. additional merchandise in form of t-shirts.'),
            'button_text': _('Create a first product'),
            'button_url': reverse('control:event.items.add', kwargs=kwargs)
        })
    elif not sender.quotas.exists():
        ctx.update({
            'subtitle': _('Create quotas that apply to your products'),
            'text': _('Your tickets will only be available for sale if you create a matching quota, i.e. if you tell '
                      'pretix how many tickets it should sell for your event.'),
            'button_text': _('Create a first quota'),
            'button_url': reverse('control:event.items.quotas.add', kwargs=kwargs)
        })
    else:
        return []
    return [{
        'display_size': 'full',
        'priority': 2000,
        'content': template.render(ctx)
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
                event=event.name, df=date_format(event.date_from, 'SHORT_DATE_FORMAT') if event.date_from else '',
                dt=date_format(event.date_to, 'SHORT_DATE_FORMAT') if event.date_to else ''
            ),
            'display_size': 'small',
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
            'display_size': 'small',
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
