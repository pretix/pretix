from collections import namedtuple

from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy

from pretix.base.reldate import RelativeDateWrapper

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
        description=pgettext_lazy('timeline', 'Event start'),
        edit_url=ev_edit_url
    ))

    if ev.date_to:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.date_to,
            description=pgettext_lazy('timeline', 'Event end'),
            edit_url=ev_edit_url
        ))

    if ev.date_admission:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=ev.date_admission,
            description=pgettext_lazy('timeline', 'Event admission'),
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

    modify_deadline = event.settings.get('last_order_modification_date', as_type=RelativeDateWrapper)
    if modify_deadline:
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=modify_deadline.datetime(ev),
            description=pgettext_lazy('timeline', 'Customers can no longer modify their orders'),
            edit_url=ev_edit_url
        ))

    tl.append(TimelineEvent(
        event=event, subevent=subevent,
        datetime=now(),
        description=pgettext_lazy('timeline', 'now'),
        edit_url=None
    ))

    # last date of payments
    # payment providers
    # product availability
    # shipping
    # ticket download
    # download reminders
    # cancellations

    return sorted(tl, key=lambda e: e.datetime)
