import datetime
from urllib.parse import urlparse

import pytz
import vobject
from django.conf import settings
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from pretix.base.models import Event
from pretix.multidomain.urlreverse import build_absolute_uri


def get_ical(events):
    cal = vobject.iCalendar()
    cal.add('prodid').value = '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME.replace(" ", "_"))
    creation_time = datetime.datetime.now(pytz.utc)

    for ev in events:
        event = ev if isinstance(ev, Event) else ev.event
        tz = pytz.timezone(event.settings.timezone)
        if isinstance(ev, Event):
            url = build_absolute_uri(event, 'presale:event.index')
        else:
            url = build_absolute_uri(event, 'presale:event.index', {
                'subevent': ev.pk
            })

        vevent = cal.add('vevent')
        vevent.add('summary').value = str(ev.name)
        vevent.add('dtstamp').value = creation_time
        if ev.location:
            vevent.add('location').value = str(ev.location)
        vevent.add('uid').value = 'pretix-{}-{}-{}@{}'.format(
            event.organizer.slug, event.slug,
            ev.pk if not isinstance(ev, Event) else '0',
            urlparse(url).netloc
        )

        if event.settings.show_times:
            vevent.add('dtstart').value = ev.date_from.astimezone(tz)
        else:
            vevent.add('dtstart').value = ev.date_from.astimezone(tz).date()

        if event.settings.show_date_to and ev.date_to:
            if event.settings.show_times:
                vevent.add('dtend').value = ev.date_to.astimezone(tz)
            else:
                # with full-day events date_to in pretix is included (e.g. last day)
                # whereas dtend in vcalendar is non-inclusive => add one day for export
                vevent.add('dtend').value = ev.date_to.astimezone(tz).date() + datetime.timedelta(days=1) 

        descr = []
        descr.append(_('Tickets: {url}').format(url=url))

        if ev.date_admission:
            descr.append(str(_('Admission: {datetime}')).format(
                datetime=date_format(ev.date_admission.astimezone(tz), 'SHORT_DATETIME_FORMAT')
            ))

        descr.append(_('Organizer: {organizer}').format(organizer=event.organizer.name))

        vevent.add('description').value = '\n'.join(descr)
    return cal
