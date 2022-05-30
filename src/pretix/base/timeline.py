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
from collections import namedtuple
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils.timezone import make_aware
from django.utils.translation import pgettext_lazy

from pretix.base.models import ItemVariation
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

    tl.append(TimelineEvent(
        event=event, subevent=subevent,
        datetime=(
            ev.presale_end or ev.date_to or ev.date_from.astimezone(ev.timezone).replace(hour=23, minute=59, second=59)
        ),
        description='{}{}'.format(
            pgettext_lazy('timeline', 'End of ticket sales'),
            f" ({pgettext_lazy('timeline', 'automatically because the event is over and no end of presale has been configured')})" if not ev.presale_end else ""
        ),
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
        d = make_aware(datetime.combine(
            rd.date(ev),
            time(hour=23, minute=59, second=59)
        ), event.timezone)
        tl.append(TimelineEvent(
            event=event, subevent=subevent,
            datetime=d,
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
            edit_url=reverse('control:event.settings.cancel', kwargs={
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
            edit_url=reverse('control:event.settings.cancel', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug
            })
        ))

    if not event.has_subevents:
        days = event.settings.get('mail_days_download_reminder', as_type=int)
        if days is not None and event.settings.ticket_download:
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

    if subevent:
        for sei in subevent.item_overrides.values():
            if sei.available_from:
                tl.append(TimelineEvent(
                    event=event, subevent=subevent,
                    datetime=sei.available_from,
                    description=pgettext_lazy('timeline', 'Product "{name}" becomes available').format(name=str(sei.item)),
                    edit_url=reverse('control:event.subevent', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'subevent': subevent.pk,
                    })
                ))
            if sei.available_until:
                tl.append(TimelineEvent(
                    event=event, subevent=subevent,
                    datetime=sei.available_until,
                    description=pgettext_lazy('timeline', 'Product "{name}" becomes unavailable').format(name=str(sei.item)),
                    edit_url=reverse('control:event.subevent', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'subevent': subevent.pk,
                    })
                ))
        for sei in subevent.var_overrides.values():
            if sei.available_from:
                tl.append(TimelineEvent(
                    event=event, subevent=subevent,
                    datetime=sei.available_from,
                    description=pgettext_lazy('timeline', 'Product "{name}" becomes available').format(
                        name=str(sei.variation.item) + ' – ' + str(sei.variation)),
                    edit_url=reverse('control:event.subevent', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'subevent': subevent.pk,
                    })
                ))
            if sei.available_until:
                tl.append(TimelineEvent(
                    event=event, subevent=subevent,
                    datetime=sei.available_until,
                    description=pgettext_lazy('timeline', 'Product "{name}" becomes unavailable').format(
                        name=str(sei.variation.item) + ' – ' + str(sei.variation)),
                    edit_url=reverse('control:event.subevent', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'subevent': subevent.pk,
                    })
                ))

    for d in event.discounts.filter(Q(available_from__isnull=False) | Q(available_until__isnull=False)):
        if d.available_from:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=d.available_from,
                description=pgettext_lazy('timeline', 'Discount "{name}" becomes active').format(name=str(d)),
                edit_url=reverse('control:event.items.discounts.edit', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'discount': d.pk,
                })
            ))
        if d.available_until:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=d.available_until,
                description=pgettext_lazy('timeline', 'Discount "{name}" becomes inactive').format(name=str(d)),
                edit_url=reverse('control:event.items.discounts.edit', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'discount': d.pk,
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

    for v in ItemVariation.objects.filter(
        Q(available_from__isnull=False) | Q(available_until__isnull=False),
        item__event=event
    ).select_related('item'):
        if v.available_from:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=v.available_from,
                description=pgettext_lazy('timeline', 'Product variation "{product} – {variation}" becomes available').format(
                    product=str(v.item),
                    variation=str(v.value),
                ),
                edit_url=reverse('control:event.item', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'item': v.item.pk,
                })
            ))
        if v.available_until:
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=v.available_until,
                description=pgettext_lazy('timeline', 'Product variation "{product} – {variation}" becomes unavailable').format(
                    product=str(v.item),
                    variation=str(v.value),
                ),
                edit_url=reverse('control:event.item', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'item': v.item.pk,
                })
            ))

    pprovs = event.get_payment_providers()
    # This is a special case, depending on payment providers not overriding BasePaymentProvider by too much, but it's
    # preferrable to having all plugins implement this spearately.
    for pprov in pprovs.values():
        if not pprov.settings.get('_enabled', as_type=bool):
            continue
        try:
            if not pprov.is_enabled:
                continue
        except:
            pass
        availability_date = pprov.settings.get('_availability_date', as_type=RelativeDateWrapper)
        if availability_date:
            d = make_aware(datetime.combine(
                availability_date.date(ev),
                time(hour=23, minute=59, second=59)
            ), event.timezone)
            tl.append(TimelineEvent(
                event=event, subevent=subevent,
                datetime=d,
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
