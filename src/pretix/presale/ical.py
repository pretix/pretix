#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from urllib.parse import urlparse

import vobject
from django.conf import settings
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

    evs = set(p.subevent or event for p in positions)
    for ev in evs:
        if isinstance(ev, Event):
            url = build_absolute_uri(event, 'presale:event.index')
        else:
            url = build_absolute_uri(event, 'presale:event.index', {
                'subevent': ev.pk
            })

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

        cal = vobject.iCalendar()
        cal.add('prodid').value = '-//pretix//{}//'.format(settings.PRETIX_INSTANCE_NAME.replace(" ", "_"))

        vevent = cal.add('vevent')
        vevent.add('summary').value = str(ev.name)
        vevent.add('description').value = description
        vevent.add('dtstamp').value = creation_time
        if ev.location:
            vevent.add('location').value = ", ".join(l.strip() for l in str(ev.location).splitlines() if l.strip())

        vevent.add('uid').value = 'pretix-{}-{}-{}@{}'.format(
            event.organizer.slug,
            event.slug,
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

        calobjects.append(cal)
    return calobjects
