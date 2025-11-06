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
import datetime
from collections import namedtuple
from urllib.parse import urlparse

import vobject
from django.conf import settings
from django.db.models import prefetch_related_objects
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from pretix.base.email import get_email_context
from pretix.base.models import Event
from pretix.helpers.format import format_map
from pretix.multidomain.urlreverse import build_absolute_uri


def get_public_ical(events):
    """
    Return an ical feed for a sequence of events or subevents. The calendar files will only include public
    information.
    """
    cal = vobject.iCalendar()
    cal.add('prodid').value = '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME.replace(" ", "_"))
    creation_time = datetime.datetime.now(datetime.timezone.utc)

    for ev in events:
        event = ev if isinstance(ev, Event) else ev.event
        tz = event.timezone
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
            vevent.add('location').value = ", ".join(l.strip() for l in str(ev.location).splitlines() if l.strip())
        vevent.add('uid').value = 'pretix-{}-{}-{}@{}'.format(
            event.organizer.slug, event.slug,
            ev.pk if not isinstance(ev, Event) else '0',
            urlparse(url).netloc
        )

        if event.settings.show_times:
            vevent.add('dtstart').value = ev.date_from.astimezone(tz)
        else:
            vevent.add('dtstart').value = ev.date_from.astimezone(tz).date()

        # always add dtend as calendar apps otherwise have display issues
        use_date_to = event.settings.show_date_to and ev.date_to
        dtend = (ev.date_to if use_date_to else ev.date_from).astimezone(tz)

        if not event.settings.show_times:
            # with full-day events date_to in pretix is included (e.g. last day)
            # whereas dtend in vcalendar is non-inclusive => add one day for export
            dtend = dtend.date() + datetime.timedelta(days=1)
        elif not use_date_to:
            # date_from used as end-date => add 1h as a default duration
            dtend = dtend + datetime.timedelta(hours=1)
        vevent.add('dtend').value = dtend

        descr = []
        descr.append(_('Tickets: {url}').format(url=url))

        if ev.date_admission:
            descr.append(str(_('Admission: {datetime}')).format(
                datetime=date_format(ev.date_admission.astimezone(tz), 'SHORT_DATETIME_FORMAT')
            ))

        descr.append(_('Organizer: {organizer}').format(organizer=event.organizer.name))
        # Actual ical organizer field is not useful since it will cause "your invitation was accepted" emails to the organizer

        vevent.add('description').value = '\n'.join(descr)
    return cal


def get_private_icals(event, positions):
    """
    Return a list of ical objects based on a sequence of positions.

    Unlike get_public_ical, this will

    - Generate multiple ical files instead of one (but with deduplication applied)
    - Respect the mail_attach_ical_description setting

    It is private in the sense that mail_attach_ical_description may contain content not suited for
    public display.

    We however intentionally do not allow using placeholders based on the order and position
    specifically. This is for two reasons:

    - In reality, many people will add their invite to their calendar which is shared with a larger
      team. People are probably not aware that they're sharing sensitive information such as their
      secret ticket link with everyone they share their calendar with.

    - It would be pretty hard to implement it in a way that doesn't require us to use distinct
      settings fields for emails to customers and to attendees, which feels like an overcomplication.
    """
    tz = event.timezone

    creation_time = datetime.datetime.now(datetime.timezone.utc)
    calobjects = []
    calentries = set()  # using set for automatic deduplication of CalEntries
    CalEntry = namedtuple('CalEntry', ['summary', 'description', 'location', 'dtstart', 'dtend', 'uid'])

    # collecting the positions' calendar entries, preferring the most exact date and time available (positions > subevent > event)
    prefetch_related_objects(positions, 'item__program_times')
    for p in positions:
        ev = p.subevent or event
        program_times = p.item.program_times.all()
        if program_times:
            # if program times have been configured, they are preferred for the position's calendar entries
            url = build_absolute_uri(event, 'presale:event.index')
            for index, pt in enumerate(program_times):
                summary = _('{event} - {item}').format(event=ev, item=p.item.name)
                if event.settings.mail_attach_ical_description:
                    ctx = get_email_context(event=event, event_or_subevent=ev)
                    description = format_map(str(event.settings.mail_attach_ical_description), ctx)
                else:
                    # Default description
                    descr = []
                    descr.append(_('Tickets: {url}').format(url=url))
                    descr.append(str(_('Start: {datetime}')).format(
                        datetime=date_format(pt.start.astimezone(tz), 'SHORT_DATETIME_FORMAT')
                    ))
                    descr.append(str(_('End: {datetime}')).format(
                        datetime=date_format(pt.end.astimezone(tz), 'SHORT_DATETIME_FORMAT')
                    ))
                    # Actual ical organizer field is not useful since it will cause "your invitation was accepted" emails to the organizer
                    descr.append(_('Organizer: {organizer}').format(organizer=event.organizer.name))
                    description = '\n'.join(descr)
                location = None
                dtstart = pt.start.astimezone(tz)
                dtend = pt.end.astimezone(tz)
                uid = 'pretix-{}-{}-{}-{}@{}'.format(
                    event.organizer.slug,
                    event.slug,
                    p.item.id,
                    index,
                    urlparse(url).netloc
                )
                calentries.add(CalEntry(summary, description, location, dtstart, dtend, uid))
        else:
            # without program times, the subevent or event times are used for calendar entries, preferring subevents
            if p.subevent:
                url = build_absolute_uri(event, 'presale:event.index', {
                    'subevent': p.subevent.pk
                })
            else:
                url = build_absolute_uri(event, 'presale:event.index')

            if event.settings.mail_attach_ical_description:
                ctx = get_email_context(event=event, event_or_subevent=ev)
                description = format_map(str(event.settings.mail_attach_ical_description), ctx)
            else:
                # Default description
                descr = []
                descr.append(_('Tickets: {url}').format(url=url))
                if ev.date_admission:
                    descr.append(str(_('Admission: {datetime}')).format(
                        datetime=date_format(ev.date_admission.astimezone(tz), 'SHORT_DATETIME_FORMAT')
                    ))

                # Actual ical organizer field is not useful since it will cause "your invitation was accepted" emails to the organizer
                descr.append(_('Organizer: {organizer}').format(organizer=event.organizer.name))
                description = '\n'.join(descr)
            summary = str(ev.name)
            if ev.location:
                location = ", ".join(l.strip() for l in str(ev.location).splitlines() if l.strip())
            else:
                location = None
            if event.settings.show_times:
                dtstart = ev.date_from.astimezone(tz)
            else:
                dtstart = ev.date_from.astimezone(tz).date()
            if event.settings.show_date_to and ev.date_to:
                if event.settings.show_times:
                    dtend = ev.date_to.astimezone(tz)
                else:
                    # with full-day events date_to in pretix is included (e.g. last day)
                    # whereas dtend in vcalendar is non-inclusive => add one day for export
                    dtend = ev.date_to.astimezone(tz).date() + datetime.timedelta(days=1)
            else:
                dtend = None
            uid = 'pretix-{}-{}-{}@{}'.format(
                event.organizer.slug,
                event.slug,
                ev.pk if p.subevent else '0',
                urlparse(url).netloc
            )
            calentries.add(CalEntry(summary, description, location, dtstart, dtend, uid))

    for calentry in calentries:
        cal = vobject.iCalendar()
        cal.add('prodid').value = '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME.replace(" ", "_"))

        vevent = cal.add('vevent')
        vevent.add('summary').value = calentry.summary
        vevent.add('description').value = calentry.description
        vevent.add('dtstamp').value = creation_time
        if calentry.location:
            vevent.add('location').value = calentry.location
        vevent.add('uid').value = calentry.uid
        vevent.add('dtstart').value = calentry.dtstart
        if calentry.dtend:
            vevent.add('dtend').value = calentry.dtend
        calobjects.append(cal)
    return calobjects
