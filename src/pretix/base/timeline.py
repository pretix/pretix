from collections import namedtuple
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import pgettext_lazy

from pretix.base.reldate import RelativeDateWrapper
from pretix.base.signals import timeline_events

TimelineEvent = namedtuple('TimelineEvent', ('event', 'subevent', 'datetime', 'description', 'edit_url'))


def timeline_for_event(event, subevent=None):
    tl = []
    ev = subevent or event
    if subevent:
        ev_edit_url = reverse(
            'control:event.subevent', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
                'subevent': subevent.pk
            }
        )
    else:
        ev_edit_url = reverse(
            'control:event.settings', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            }
        )

    tl.append(TimelineEvent(
        event=event, subevent=subevent,
        datetime=ev.date_from,
        description=pgettext_lazy('timeline', 'Your event starts'),
        edit_url=ev_edit_url
    ))

    if ev.date_to:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.date_to,
            description=pgettext_lazy('timeline', 'Your event ends'),
            edit_url=ev_edit_url
        ))

    if ev.date_admission:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.date_admission,
            description=pgettext_lazy('timeline', 'Admissions for your event start'),
            edit_url=ev_edit_url
        ))

    if ev.presale_start:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.presale_start,
            description=pgettext_lazy('timeline', 'Start of ticket sales'),
            edit_url=ev_edit_url
        ))

    if ev.presale_end:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.presale_end,
            description=pgettext_lazy('timeline', 'End of ticket sales'),
            edit_url=ev_edit_url
        ))

    rd = event.settings.get('last_order_modification_date', as_type=RelativeDateWrapper)
    if rd:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=rd.datetime(ev),
            description=pgettext_lazy('timeline', 'Customers can no longer modify their orders'),
            edit_url=ev_edit_url
        ))

    rd = event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
    if rd:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=rd.datetime(ev),
            description=pgettext_lazy('timeline', 'No more payments can be completed'),
            edit_url=reverse('control:event.settings.payment', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        ))

    rd = event.settings.get('ticket_download_date', as_type=RelativeDateWrapper)
    if rd and event.settings.ticket_download:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=rd.datetime(ev),
            description=pgettext_lazy('timeline', 'Tickets can be downloaded'),
            edit_url=reverse('control:event.settings.tickets', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        ))

    rd = event.settings.get('cancel_allow_user_until', as_type=RelativeDateWrapper)
    if rd and event.settings.cancel_allow_user:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=rd.datetime(ev),
            description=pgettext_lazy('timeline', 'Customers can no longer cancel free or unpaid orders'),
            edit_url=reverse('control:event.settings.tickets', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        ))

    rd = event.settings.get('cancel_allow_user_paid_until', as_type=RelativeDateWrapper)
    if rd and event.settings.cancel_allow_user_paid:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=rd.datetime(ev),
            description=pgettext_lazy('timeline', 'Customers can no longer cancel paid orders'),
            edit_url=reverse('control:event.settings.tickets', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        ))

    if not event.has_subevents:
        days = event.settings.get('mail_days_download_reminder', as_type=int)
        if days is not None:
            reminder_date = (ev.date_from - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=reminder_date,
                description=pgettext_lazy('timeline', 'Download reminders are being sent out'),
                edit_url=reverse('control:event.settings.mail', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug
                })
            ))

    for p in event.items.filter(Q(available_from__isnull=False) | Q(available_until__isnull=False)):
        if p.available_from:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=p.available_from,
                description=pgettext_lazy('timeline', 'Product "{name}" becomes available').format(name=str(p)),
                edit_url=reverse('control:event.item', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'item': p.pk,
                })
            ))
        if p.available_until:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=p.available_until,
                description=pgettext_lazy('timeline', 'Product "{name}" becomes unavailable').format(name=str(p)),
                edit_url=reverse('control:event.item', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'item': p.pk,
                })
            ))

    pprovs = event.get_payment_providers()
    # This is a special case, depending on payment providers not overriding BasePaymentProvider by too much, but it's
    # preferrable to having all plugins implement this spearately.
    for pprov in pprovs.values():
        availability_date = pprov.settings.get('_availability_date', as_type=RelativeDateWrapper)
        if availability_date:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=availability_date.datetime(ev),
                description=pgettext_lazy('timeline', 'Payment provider "{name}" can no longer be selected').format(
                    name=str(pprov.verbose_name)
                ),
                edit_url=reverse('control:event.settings.payment.provider', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'provider': pprov.identifier,
                })
            ))

    for recv, resp in timeline_events.send(sender=event, subevent=subevent):
        tl += resp

    return sorted(tl, key=lambda e: e.datetime)
