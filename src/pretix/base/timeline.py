from collections import namedtuple

from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy

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

    tl.append(TimelineEvent(
        event=event, subevent=subevent,
        datetime=now(),
        description=pgettext_lazy('timeline', 'now'),
        edit_url=None
    ))

    return sorted(tl, key=lambda e: e.datetime)
