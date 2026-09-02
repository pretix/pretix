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
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils.timezone import make_aware, now

from pretix.base.models import Event, SalesChannel
from pretix.base.reldate import RelativeDateWrapper


def compute_payment_deadline(event: Event, sales_channel: SalesChannel, now_dt=None, subevents=None) -> datetime:
    now_dt = now_dt or now()
    tz = ZoneInfo(event.settings.timezone)

    sales_channel_suffix = "_" + sales_channel.identifier.replace(".", "_")
    if not (mode := event.settings.get(f'payment_term_mode{sales_channel_suffix}')):
        mode = event.settings.get('payment_term_mode')
        sales_channel_suffix = ""

    if mode == 'days':
        exp_by_date = now_dt.astimezone(tz) + timedelta(
            days=event.settings.get(f'payment_term_days{sales_channel_suffix}', as_type=int))
        exp_by_date = exp_by_date.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=0)
        if event.settings.get('payment_term_weekdays'):
            if exp_by_date.weekday() == 5:
                exp_by_date += timedelta(days=2)
            elif exp_by_date.weekday() == 6:
                exp_by_date += timedelta(days=1)
    elif mode == 'minutes':
        exp_by_date = now_dt.astimezone(tz) + timedelta(
            minutes=event.settings.get(f'payment_term_minutes{sales_channel_suffix}', as_type=int))
    else:
        raise ValueError("'payment_term_mode' has an invalid value '{}'.".format(mode))

    expires = exp_by_date

    term_last = event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
    if term_last:
        if event.has_subevents and subevents:
            terms = [
                term_last.datetime(se).date()
                for se in subevents
            ]
            if not terms:
                return expires
            term_last = min(terms)
        else:
            term_last = term_last.datetime(event).date()
        term_last = make_aware(datetime.combine(
            term_last,
            time(hour=23, minute=59, second=59)
        ), tz)
        if term_last < expires:
            return term_last

    return expires
