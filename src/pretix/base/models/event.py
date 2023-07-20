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

import logging
# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Aiman Parvaiz, Christopher Dambamuromo, Joepriesto,
# Matthew Emerson, Mohit Jindal, Sohalt, Tobias Kunze, Ture Gjørup, jasonwaiting@live.hk, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import os
import string
import uuid
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, time, timedelta
from operator import attrgetter
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pytz_deprecation_shim
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.mail import get_connection
from django.core.validators import (
    MaxValueValidator, MinValueValidator, RegexValidator,
)
from django.db import models
from django.db.models import Exists, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.template.defaultfilters import date as _date
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext, gettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.models.base import LoggedModel
from pretix.base.models.fields import MultiStringField
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.validators import EventSlugBanlistValidator
from pretix.helpers.database import GroupConcat
from pretix.helpers.daterange import daterange
from pretix.helpers.hierarkey import clean_filename
from pretix.helpers.json import safe_string
from pretix.helpers.thumb import get_thumbnail

from ..settings import settings_hierarkey
from .organizer import Organizer, Team

logger = logging.getLogger(__name__)


class EventMixin:
    def clean(self):
        if self.presale_start and self.presale_end and self.presale_start > self.presale_end:
            raise ValidationError({'presale_end': _('The end of the presale period has to be later than its start.')})
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError({'date_to': _('The end of the event has to be later than its start.')})
        super().clean()

    def get_short_date_from_display(self, tz=None, show_times=True) -> str:
        """
        Returns a shorter formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz),
            "SHORT_DATETIME_FORMAT" if self.settings.show_times and show_times else "DATE_FORMAT"
        )

    def get_short_date_to_display(self, tz=None) -> str:
        """
        Returns a shorter formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz),
            "SHORT_DATETIME_FORMAT" if self.settings.show_times else "DATE_FORMAT"
        )

    def get_date_from_display(self, tz=None, show_times=True, short=False) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz),
            ("SHORT_" if short else "") + ("DATETIME_FORMAT" if self.settings.show_times and show_times else "DATE_FORMAT")
        )

    def get_weekday_from_display(self, tz=None, short=False) -> str:
        """
        Returns a formatted string containing the weekday of the start date of the event with respect
        to the current locale.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz), ("D" if short else "l")
        )

    def get_time_from_display(self, tz=None) -> str:
        """
        Returns a formatted string containing the start time of the event, ignoring
        the ``show_times`` setting.
        """
        tz = tz or self.timezone
        return _date(
            self.date_from.astimezone(tz), "TIME_FORMAT"
        )

    def get_date_to_display(self, tz=None, show_times=True, short=False) -> str:
        """
        Returns a formatted string containing the start date of the event with respect
        to the current locale and to the ``show_times`` setting. Returns an empty string
        if ``show_date_to`` is ``False``.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz),
            ("SHORT_" if short else "") + ("DATETIME_FORMAT" if self.settings.show_times and show_times else "DATE_FORMAT")
        )

    def get_weekday_to_display(self, tz=None, short=False) -> str:
        """
        Returns a formatted string containing the weekday of the end date of the event with respect
        to the current locale.
        """
        tz = tz or self.timezone
        if not self.settings.show_date_to or not self.date_to:
            return ""
        return _date(
            self.date_to.astimezone(tz), ("D" if short else "l")
        )

    def get_date_range_display(self, tz=None, force_show_end=False, as_html=False) -> str:
        """
        Returns a formatted string containing the start date and the end date
        of the event with respect to the current locale and to the ``show_date_to``
        setting. Times are not shown.
        """
        tz = tz or self.timezone
        if (not self.settings.show_date_to and not force_show_end) or not self.date_to:
            if as_html:
                return format_html(
                    "<time datetime=\"{}\">{}</time>",
                    _date(self.date_from.astimezone(tz), "Y-m-d"),
                    _date(self.date_from.astimezone(tz), "DATE_FORMAT"),
                )
            return _date(self.date_from.astimezone(tz), "DATE_FORMAT")
        return daterange(self.date_from.astimezone(tz), self.date_to.astimezone(tz), as_html)

    def get_date_range_display_as_html(self, tz=None, force_show_end=False) -> str:
        return self.get_date_range_display(tz, force_show_end, as_html=True)

    def get_time_range_display(self, tz=None, force_show_end=False) -> str:
        """
        Returns a formatted string containing the start time and sometimes the end time
        of the event with respect to the current locale and to the ``show_date_to``
        setting. Dates are not shown. This is usually used in combination with get_date_range_display
        """
        tz = tz or self.timezone

        show_date_to = self.date_to and (self.settings.show_date_to or force_show_end) and (
            # Show date to if start and end are on the same day ("08:00-10:00")
            self.date_to.astimezone(tz).date() == self.date_from.astimezone(tz).date() or
            # Show date to if start and end are on consecutive days and less than 24h ("23:00-03:00")
            (self.date_to.astimezone(tz).date() == self.date_from.astimezone(tz).date() + timedelta(days=1) and
             self.date_to.astimezone(tz).time() < self.date_from.astimezone(tz).time())
            # Do not show end time if this is a 5-day event because there's no way to make it understandable
        )
        if show_date_to:
            return '{} – {}'.format(
                _date(self.date_from.astimezone(tz), "TIME_FORMAT"),
                _date(self.date_to.astimezone(tz), "TIME_FORMAT"),
            )
        return _date(self.date_from.astimezone(tz), "TIME_FORMAT")

    @property
    def timezone(self):
        return pytz_deprecation_shim.timezone(self.settings.timezone)

    @property
    def effective_presale_end(self):
        """
        Returns the effective presale end date, taking for subevents into consideration if the presale end
        date might have been further limited by the event-level presale end date
        """
        if isinstance(self, SubEvent):
            presale_ends = [self.presale_end, self.event.presale_end]
            return min(filter(lambda x: x is not None, presale_ends)) if any(presale_ends) else None
        else:
            return self.presale_end

    @property
    def presale_has_ended(self):
        """
        Is true, when ``presale_end`` is set and in the past.
        """
        if self.effective_presale_end:
            return now() > self.effective_presale_end
        elif self.date_to:
            return now() > self.date_to
        else:
            return now().astimezone(self.timezone).date() > self.date_from.astimezone(self.timezone).date()

    @property
    def effective_presale_start(self):
        """
        Returns the effective presale start date, taking for subevents into consideration if the presale start
        date might have been further limited by the event-level presale start date
        """
        if isinstance(self, SubEvent):
            presale_starts = [self.presale_start, self.event.presale_start]
            return max(filter(lambda x: x is not None, presale_starts)) if any(presale_starts) else None
        else:
            return self.presale_start

    @property
    def presale_is_running(self):
        """
        Is true, when ``presale_end`` is not set or in the future and ``presale_start`` is not
        set or in the past.
        """
        if self.effective_presale_start and now() < self.effective_presale_start:
            return False
        return not self.presale_has_ended

    @property
    def event_microdata(self):
        import json

        eventdict = {
            "@context": "http://schema.org",
            "@type": "Event", "location": {
                "@type": "Place",
                "address": str(self.location),
            },
            "name": str(self.name),
        }
        img = getattr(self, 'event', self).social_image
        if img:
            eventdict['image'] = img

        if self.settings.show_times:
            eventdict["startDate"] = self.date_from.isoformat()
            if self.settings.show_date_to and self.date_to is not None:
                eventdict["endDate"] = self.date_to.isoformat()
        else:
            eventdict["startDate"] = self.date_from.date().isoformat()
            if self.settings.show_date_to and self.date_to is not None:
                eventdict["endDate"] = self.date_to.date().isoformat()

        return safe_string(json.dumps(eventdict))

    @classmethod
    def annotated(cls, qs, channel='web', voucher=None):
        from pretix.base.models import Item, ItemVariation, Quota

        sq_active_item = Item.objects.using(settings.DATABASE_REPLICA).filter_available(channel=channel, voucher=voucher).filter(
            Q(variations__isnull=True)
            & Q(quotas__pk=OuterRef('pk'))
        ).order_by().values_list('quotas__pk').annotate(
            items=GroupConcat('pk', delimiter=',')
        ).values('items')

        q_variation = (
            Q(active=True)
            & Q(sales_channels__contains=channel)
            & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
            & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
            & Q(item__active=True)
            & Q(Q(item__available_from__isnull=True) | Q(item__available_from__lte=now()))
            & Q(Q(item__available_until__isnull=True) | Q(item__available_until__gte=now()))
            & Q(Q(item__category__isnull=True) | Q(item__category__is_addon=False))
            & Q(item__sales_channels__contains=channel)
            & Q(item__require_bundling=False)
            & Q(quotas__pk=OuterRef('pk'))
        )

        if voucher:
            if voucher.variation_id:
                q_variation &= Q(pk=voucher.variation_id)
            elif voucher.item_id:
                q_variation &= Q(item_id=voucher.item_id)
            elif voucher.quota_id:
                q_variation &= Q(quotas__in=[voucher.quota_id])

        if not voucher or not voucher.show_hidden_items:
            q_variation &= Q(hide_without_voucher=False)
            q_variation &= Q(item__hide_without_voucher=False)

        sq_active_variation = ItemVariation.objects.filter(q_variation).order_by().values_list('quotas__pk').annotate(
            items=GroupConcat('pk', delimiter=',')
        ).values('items')
        quota_base_qs = Quota.objects.using(settings.DATABASE_REPLICA).filter(
            ignore_for_event_availability=False
        )

        if cls is Event:
            # Special case for the list of events: We only want to compute quotas for events if they are
            # not an event series.
            quota_base_qs = quota_base_qs.filter(subevent__isnull=True)

        return qs.annotate(
            has_paid_item=Exists(Item.objects.filter(event_id=OuterRef(cls._event_id), default_price__gt=0))
        ).prefetch_related(
            Prefetch(
                'quotas',
                to_attr='active_quotas',
                queryset=quota_base_qs.annotate(
                    active_items=Subquery(sq_active_item, output_field=models.TextField()),
                    active_variations=Subquery(sq_active_variation, output_field=models.TextField()),
                ).exclude(
                    Q(active_items="") & Q(active_variations="")
                ).select_related('event', 'subevent')
            )
        )

    @property
    def best_availability_state(self):
        return self.best_availability[0]

    @property
    def best_availability_is_low(self):
        """
        Returns ``True`` if the availability of tickets in this event is lower than the percentage
        given in setting ``low_availability_percentage``.
        """
        if not self.settings.low_availability_percentage:
            return False
        ba = self.best_availability
        if ba[1] is None or not ba[2]:
            return False

        percentage = ba[1] / ba[2] * 100
        return percentage < self.settings.low_availability_percentage

    @cached_property
    def best_availability(self):
        """
        Returns a 3-tuple of

        - The availability state of this event (one of the ``Quota.AVAILABILITY_*`` constants)
        - The number of tickets currently available (or ``None``)
        - The number of tickets "originally" available (or ``None``)

        This can only be called on objects obtained through a queryset that has been passed through ``.annotated()``.
        """
        from .items import Quota

        if not hasattr(self, 'active_quotas'):
            raise TypeError("Call this only if you fetched the subevents via Event/SubEvent.annotated()")

        if hasattr(self, 'disabled_items'):  # SubEventItem
            items_disabled = set(self.disabled_items.split(","))
        else:
            items_disabled = set()

        if hasattr(self, 'disabled_vars'):  # SubEventItemVariation
            vars_disabled = set(self.disabled_vars.split(","))
        else:
            vars_disabled = set()

        # Compute the availability of all quotas and build a item→quotas mapping with all non-disabled items
        r = getattr(self, '_quota_cache', {})
        quotas_for_item = defaultdict(list)
        quotas_for_variation = defaultdict(list)
        for q in self.active_quotas:
            if q not in r:
                r[q] = q.availability(allow_cache=True)

            if q.active_items:
                for item_id in q.active_items.split(","):
                    if item_id not in items_disabled:
                        quotas_for_item[item_id].append(q)
            if q.active_variations:
                for var_id in q.active_variations.split(","):
                    if var_id not in vars_disabled:
                        quotas_for_variation[var_id].append(q)

        if not self.active_quotas or (not quotas_for_item and not quotas_for_variation):
            # No item is enabled for this event, treat the event as "unknown"
            return None, None, None

        # We iterate over all items and variations and keep track of
        # - `best_state_found` - the best availability state we have seen so far. If one item is available, the event is available!
        # - `num_tickets_found` - the number of tickets currently available in total. We sum up all the items and variations, but keep
        #   track of them per-quota in `quota_used_for_found_tickets` to make sure we don't count the same tickets twice if two or more
        #   items share the same quota
        # - `num_tickets_possible` - basically the same thing, just with the total size of quotas instead of their currently availability
        #   since we need that for the percentage calculation
        best_state_found = Quota.AVAILABILITY_GONE
        num_tickets_found = 0
        num_tickets_possible = 0
        quota_used_for_found_tickets = Counter()
        quota_used_for_possible_tickets = Counter()
        for quota_list in list(quotas_for_item.values()) + list(quotas_for_variation.values()):
            worst_state_for_ticket = min(r[q][0] for q in quota_list)
            quotas_that_are_not_unlimited = [q for q in quota_list if q.size is not None]
            if not quotas_that_are_not_unlimited:
                # We found an unlimited ticket, no more need to do anything else
                return Quota.AVAILABILITY_OK, None, None

            if worst_state_for_ticket == Quota.AVAILABILITY_OK:
                availability_of_this = min(max(0, r[q][1] - quota_used_for_found_tickets[q]) for q in quotas_that_are_not_unlimited)
                num_tickets_found += availability_of_this
                for q in quota_list:
                    quota_used_for_found_tickets[q] += availability_of_this

            possible_of_this = min(max(0, q.size - quota_used_for_possible_tickets[q]) for q in quotas_that_are_not_unlimited)
            num_tickets_possible += possible_of_this
            for q in quota_list:
                quota_used_for_possible_tickets[q] += possible_of_this

            best_state_found = max(best_state_found, worst_state_for_ticket)
        return best_state_found, num_tickets_found, num_tickets_possible

    def free_seats(self, ignore_voucher=None, sales_channel='web', include_blocked=False):
        qs_annotated = self._seats(ignore_voucher=ignore_voucher)

        qs = qs_annotated.filter(has_order=False, has_cart=False, has_voucher=False)
        if self.settings.seating_minimal_distance > 0:
            qs = qs.filter(has_closeby_taken=False)

        if not (sales_channel in self.settings.seating_allow_blocked_seats_for_channel or include_blocked):
            qs = qs.filter(blocked=False)
        return qs

    def total_seats(self, ignore_voucher=None):
        return self._seats(ignore_voucher=ignore_voucher)

    def taken_seats(self, ignore_voucher=None):
        return self._seats(ignore_voucher=ignore_voucher).filter(has_order=True)

    def blocked_seats(self, ignore_voucher=None):
        qs = self._seats(ignore_voucher=ignore_voucher)
        q = (
            Q(has_cart=True)
            | Q(has_voucher=True)
            | Q(blocked=True)
        )
        if self.settings.seating_minimal_distance > 0:
            q |= Q(has_closeby_taken=True, has_order=False)
        return qs.filter(q)


def default_sales_channels():
    from ..channels import get_all_sales_channels

    return list(get_all_sales_channels().keys())


@settings_hierarkey.add(parent_field='organizer', cache_namespace='event')
class Event(EventMixin, LoggedModel):
    """
    This model represents an event. An event is anything you can buy
    tickets for.

    :param organizer: The organizer this event belongs to
    :type organizer: Organizer
    :param testmode: This event is in test mode
    :type testmode: bool
    :param name: This event's full title
    :type name: str
    :param slug: A short, alphanumeric, all-lowercase name for use in URLs. The slug has to
                 be unique among the events of the same organizer.
    :type slug: str
    :param live: Whether or not the shop is publicly accessible
    :type live: bool
    :param currency: The currency of all prices and payments of this event
    :type currency: str
    :param date_from: The datetime this event starts
    :type date_from: datetime
    :param date_to: The datetime this event ends
    :type date_to: datetime
    :param presale_start: No tickets will be sold before this date.
    :type presale_start: datetime
    :param presale_end: No tickets will be sold after this date.
    :type presale_end: datetime
    :param location: venue
    :type location: str
    :param plugins: A comma-separated list of plugin names that are active for this
                    event.
    :type plugins: str
    :param has_subevents: Enable event series functionality
    :type has_subevents: bool
    :param sales_channels: A list of sales channel identifiers, that this event is available for sale on
    :type sales_channels: list
    """

    settings_namespace = 'event'
    _event_id = 'pk'
    CURRENCY_CHOICES = [(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES]
    organizer = models.ForeignKey(Organizer, related_name="events", on_delete=models.PROTECT)
    testmode = models.BooleanField(default=False)
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Event name"),
    )
    slug = models.CharField(
        max_length=50, db_index=True,
        help_text=_(
            "Should be short, only contain lowercase letters, numbers, dots, and dashes, and must be unique among your "
            "events. We recommend some kind of abbreviation or a date with less than 10 characters that can be easily "
            "remembered, but you can also choose to use a random value. "
            "This will be used in URLs, order codes, invoice numbers, and bank transfer references."),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$",
                message=_("The slug may only contain letters, numbers, dots and dashes."),
            ),
            EventSlugBanlistValidator()
        ],
        verbose_name=_("Short form"),
    )
    live = models.BooleanField(default=False, verbose_name=_("Shop is live"))
    currency = models.CharField(max_length=10,
                                verbose_name=_("Event currency"),
                                choices=CURRENCY_CHOICES,
                                default=settings.DEFAULT_CURRENCY)
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    date_admission = models.DateTimeField(null=True, blank=True,
                                          verbose_name=_("Admission time"))
    is_public = models.BooleanField(default=True,
                                    verbose_name=_("Show in lists"),
                                    help_text=_("If selected, this event will show up publicly on the list of events for your organizer account."))
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("Optional. No products will be sold after this date. If you do not set this value, the presale "
                    "will end after the end date of your event."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("Optional. No products will be sold before this date."),
    )
    location = I18nTextField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_("Location"),
    )
    geo_lat = models.FloatField(
        verbose_name=_("Latitude"),
        null=True, blank=True,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ]
    )
    geo_lon = models.FloatField(
        verbose_name=_("Longitude"),
        null=True, blank=True,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ]
    )
    plugins = models.TextField(
        null=False, blank=True,
        verbose_name=_("Plugins"),
    )
    comment = models.TextField(
        verbose_name=_("Internal comment"),
        null=True, blank=True
    )
    has_subevents = models.BooleanField(
        verbose_name=_('Event series'),
        default=False
    )
    seating_plan = models.ForeignKey('SeatingPlan', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='events', verbose_name=_('Seating plan'))

    last_modified = models.DateTimeField(
        auto_now=True, db_index=True
    )

    sales_channels = MultiStringField(
        verbose_name=_('Restrict to specific sales channels'),
        help_text=_('Only sell tickets for this event on the following sales channels.'),
        default=default_sales_channels,
    )

    objects = ScopedManager(organizer='organizer')

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        ordering = ("date_from", "name", "slug")
        unique_together = (('organizer', 'slug'),)

    def __str__(self):
        return str(self.name)

    def set_defaults(self):
        """
        This will be called after event creation, but only if the event was not created by copying an existing one.
        This way, we can use this to introduce new default settings to pretix that do not affect existing events.
        """
        self.settings.invoice_renderer = 'modern1'
        self.settings.invoice_include_expire_date = True
        self.settings.invoice_renderer_highlight_order_code = True
        self.settings.ticketoutput_pdf__enabled = True
        self.settings.ticketoutput_passbook__enabled = True
        self.settings.event_list_type = 'calendar'
        self.settings.invoice_email_attachment = True
        self.settings.name_scheme = 'given_family'
        self.settings.payment_banktransfer_invoice_immediately = True
        self.settings.low_availability_percentage = 10

    @property
    def social_image(self):
        from pretix.multidomain.urlreverse import build_absolute_uri

        img = None
        logo_file = self.settings.get('logo_image', as_type=str, default='')[7:]
        og_file = self.settings.get('og_image', as_type=str, default='')[7:]
        if og_file:
            try:
                img = get_thumbnail(og_file, '1200').thumb.url
            except:
                logger.exception(f'Failed to create thumbnail of {og_file}')
                img = default_storage.url(og_file)
        elif logo_file:
            try:
                img = get_thumbnail(logo_file, '5000x1200').thumb.url
            except:
                logger.exception(f'Failed to create thumbnail of {logo_file}')
                img = default_storage.url(logo_file)
        if img:
            return urljoin(build_absolute_uri(self, 'presale:event.index'), img)

    def _seats(self, ignore_voucher=None):
        from .seating import Seat

        qs_annotated = Seat.annotated(self.seats, self.pk, None,
                                      ignore_voucher_id=ignore_voucher.pk if ignore_voucher else None,
                                      minimal_distance=self.settings.seating_minimal_distance,
                                      distance_only_within_row=self.settings.seating_distance_within_row)

        return qs_annotated

    @property
    def presale_has_ended(self):
        if self.has_subevents:
            return self.presale_end and now() > self.presale_end
        else:
            return super().presale_has_ended

    def delete_all_orders(self, really=False):
        from .checkin import Checkin
        from .orders import (
            OrderFee, OrderPayment, OrderPosition, OrderRefund, Transaction,
        )

        if not really:
            raise TypeError("Pass really=True as a parameter.")

        Transaction.objects.filter(order__event=self).delete()
        OrderPosition.all.filter(order__event=self, addon_to__isnull=False).delete()
        OrderPosition.all.filter(order__event=self).delete()
        OrderFee.objects.filter(order__event=self).delete()
        OrderRefund.objects.filter(order__event=self).delete()
        OrderPayment.objects.filter(order__event=self).delete()
        Checkin.objects.filter(list__event=self).delete()
        self.orders.all().delete()

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        self.cache.clear()
        return obj

    def get_plugins(self):
        """
        Returns the names of the plugins activated for this event as a list.
        """
        if self.plugins is None:
            return []
        return self.plugins.split(",")

    def get_cache(self):
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.

        .. deprecated:: 1.9
           Use the property ``cache`` instead.
        """
        return self.cache

    @cached_property
    def cache(self):
        """
        Returns an :py:class:`ObjectRelatedCache` object. This behaves equivalent to
        Django's built-in cache backends, but puts you into an isolated environment for
        this event, so you don't have to prefix your cache keys. In addition, the cache
        is being cleared every time the event or one of its related objects change.
        """
        from pretix.base.cache import ObjectRelatedCache

        return ObjectRelatedCache(self)

    def lock(self):
        """
        Returns a contextmanager that can be used to lock an event for bookings.
        """
        from pretix.base.services import locking

        return locking.LockManager(self)

    def get_mail_backend(self, timeout=None):
        """
        Returns an email server connection, either by using the system-wide connection
        or by returning a custom one based on the event's settings.
        """

        if self.settings.smtp_use_custom:
            return get_connection(backend=settings.EMAIL_CUSTOM_SMTP_BACKEND,
                                  host=self.settings.smtp_host,
                                  port=self.settings.smtp_port,
                                  username=self.settings.smtp_username,
                                  password=self.settings.smtp_password,
                                  use_tls=self.settings.smtp_use_tls,
                                  use_ssl=self.settings.smtp_use_ssl,
                                  fail_silently=False,
                                  timeout=timeout)
        else:
            return get_connection(fail_silently=False)

    @property
    def payment_term_last(self):
        """
        The last datetime of payments for this event.
        """
        tz = ZoneInfo(self.settings.timezone)
        return make_aware(datetime.combine(
            self.settings.get('payment_term_last', as_type=RelativeDateWrapper).datetime(self).date(),
            time(hour=23, minute=59, second=59)
        ), tz)

    def copy_data_from(self, other):
        from pretix.presale.style import regenerate_css

        from ..signals import event_copy_data
        from . import (
            Discount, Item, ItemAddOn, ItemBundle, ItemCategory, ItemMetaValue,
            ItemVariationMetaValue, Question, Quota,
        )

        #  Note: avoid self.set_active_plugins(), it causes trouble e.g. for the badges plugin.
        #  Plugins can create data in installed() hook based on existing data of the event.
        #  Calling set_active_plugins() results in defaults being created while actually data
        #  should come from the copied event. Instead plugins should use event_copy_data to move
        #  over their data.
        self.plugins = other.plugins
        self.is_public = other.is_public
        if other.date_admission:
            self.date_admission = self.date_from + (other.date_admission - other.date_from)
        self.testmode = other.testmode
        self.sales_channels = other.sales_channels
        self.save()
        self.log_action('pretix.object.cloned', data={'source': other.slug, 'source_id': other.pk})

        for fl in EventFooterLink.objects.filter(event=other):
            fl.pk = None
            fl.event = self
            fl.save(force_insert=True)

        tax_map = {}
        for t in other.tax_rules.all():
            tax_map[t.pk] = t
            t.pk = None
            t.event = self
            t.save(force_insert=True)
            t.log_action('pretix.object.cloned')

        category_map = {}
        for c in ItemCategory.objects.filter(event=other):
            category_map[c.pk] = c
            c.pk = None
            c.event = self
            c.save(force_insert=True)
            c.log_action('pretix.object.cloned')

        item_meta_properties_map = {}
        for imp in other.item_meta_properties.all():
            item_meta_properties_map[imp.pk] = imp
            imp.pk = None
            imp.event = self
            imp.save(force_insert=True)
            imp.log_action('pretix.object.cloned')

        item_map = {}
        variation_map = {}
        for i in Item.objects.filter(event=other).prefetch_related('variations'):
            vars = list(i.variations.all())
            require_membership_types = list(i.require_membership_types.all())
            item_map[i.pk] = i
            i.pk = None
            i.event = self
            if i.picture:
                i.picture.save(os.path.basename(i.picture.name), i.picture)
            if i.category_id:
                i.category = category_map[i.category_id]
            if i.tax_rule_id:
                i.tax_rule = tax_map[i.tax_rule_id]

            if i.grant_membership_type and other.organizer_id != self.organizer_id:
                i.grant_membership_type = None

            i.save()  # no force_insert since i.picture.save could have already inserted
            i.log_action('pretix.object.cloned')

            if require_membership_types and other.organizer_id == self.organizer_id:
                i.require_membership_types.set(require_membership_types)

            for v in vars:
                variation_map[v.pk] = v
                v.pk = None
                v.item = i
                v.save(force_insert=True)

        for imv in ItemMetaValue.objects.filter(item__event=other):
            imv.pk = None
            imv.property = item_meta_properties_map[imv.property_id]
            imv.item = item_map[imv.item.pk]
            imv.save(force_insert=True)

        for imv in ItemVariationMetaValue.objects.filter(variation__item__event=other):
            imv.pk = None
            imv.property = item_meta_properties_map[imv.property_id]
            imv.variation = variation_map[imv.variation_id]
            imv.save(force_insert=True)

        for ia in ItemAddOn.objects.filter(base_item__event=other).prefetch_related('base_item', 'addon_category'):
            ia.pk = None
            ia.base_item = item_map[ia.base_item.pk]
            ia.addon_category = category_map[ia.addon_category.pk]
            ia.save(force_insert=True)

        for ia in ItemBundle.objects.filter(base_item__event=other).prefetch_related('base_item', 'bundled_item', 'bundled_variation'):
            ia.pk = None
            ia.base_item = item_map[ia.base_item.pk]
            ia.bundled_item = item_map[ia.bundled_item.pk]
            if ia.bundled_variation:
                ia.bundled_variation = variation_map[ia.bundled_variation.pk]
            ia.save(force_insert=True)

        quota_map = {}
        for q in Quota.objects.filter(event=other, subevent__isnull=True).prefetch_related('items', 'variations'):
            quota_map[q.pk] = q
            items = list(q.items.all())
            vars = list(q.variations.all())
            oldid = q.pk
            q.pk = None
            q.event = self
            q.closed = False
            q.save(force_insert=True)
            q.log_action('pretix.object.cloned')
            for i in items:
                if i.pk in item_map:
                    q.items.add(item_map[i.pk])
            for v in vars:
                q.variations.add(variation_map[v.pk])
            self.items.filter(hidden_if_available_id=oldid).update(hidden_if_available=q)

        for d in Discount.objects.filter(event=other).prefetch_related('condition_limit_products'):
            items = list(d.condition_limit_products.all())
            d.pk = None
            d.event = self
            d.save(force_insert=True)
            d.log_action('pretix.object.cloned')
            for i in items:
                if i.pk in item_map:
                    d.condition_limit_products.add(item_map[i.pk])

        question_map = {}
        for q in Question.objects.filter(event=other).prefetch_related('items', 'options'):
            items = list(q.items.all())
            opts = list(q.options.all())
            question_map[q.pk] = q
            q.pk = None
            q.event = self
            q.save(force_insert=True)
            q.log_action('pretix.object.cloned')

            for i in items:
                q.items.add(item_map[i.pk])
            for o in opts:
                o.pk = None
                o.question = q
                o.save(force_insert=True)

        for q in self.questions.filter(dependency_question__isnull=False):
            q.dependency_question = question_map[q.dependency_question_id]
            q.save(update_fields=['dependency_question'])

        def _walk_rules(rules):
            if isinstance(rules, dict):
                for k, v in rules.items():
                    if k == 'lookup':
                        if rules[k][0] == 'product':
                            rules[k][1] = str(item_map.get(int(v[1]), 0).pk) if int(v[1]) in item_map else "0"
                        elif rules[k][0] == 'variation':
                            rules[k][1] = str(variation_map.get(int(v[1]), 0).pk) if int(v[1]) in variation_map else "0"
                    else:
                        _walk_rules(v)
            elif isinstance(rules, list):
                for i in rules:
                    _walk_rules(i)

        checkin_list_map = {}
        for cl in other.checkin_lists.filter(subevent__isnull=True).prefetch_related('limit_products'):
            items = list(cl.limit_products.all())
            checkin_list_map[cl.pk] = cl
            cl.pk = None
            cl.event = self
            rules = cl.rules
            _walk_rules(rules)
            cl.rules = rules
            cl.save(force_insert=True)
            cl.log_action('pretix.object.cloned')
            for i in items:
                cl.limit_products.add(item_map[i.pk])

        if other.seating_plan:
            if other.seating_plan.organizer_id == self.organizer_id:
                self.seating_plan = other.seating_plan
            else:
                sp = other.seating_plan
                sp.pk = None
                sp.organizer = self.organizer
                sp.save(force_insert=True)
                self.seating_plan = sp
            self.save()

        for m in other.seat_category_mappings.filter(subevent__isnull=True):
            m.pk = None
            m.event = self
            m.product = item_map[m.product_id]
            m.save(force_insert=True)

        for s in other.seats.filter(subevent__isnull=True):
            s.pk = None
            s.event = self
            if s.product_id:
                s.product = item_map[s.product_id]
            s.save(force_insert=True)

        has_custom_style = other.settings.presale_css_file or other.settings.presale_widget_css_file
        skip_settings = (
            'ticket_secrets_pretix_sig1_pubkey',
            'ticket_secrets_pretix_sig1_privkey',
            'presale_css_file',
            'presale_css_checksum',
            'presale_widget_css_file',
            'presale_widget_css_checksum',
        )
        for s in other.settings._objects.all():
            if s.key in skip_settings:
                continue

            s.object = self
            s.pk = None
            if s.value.startswith('file://'):
                fi = default_storage.open(s.value[len('file://'):], 'rb')
                nonce = get_random_string(length=8)
                fname_base = clean_filename(os.path.basename(s.value))

                # TODO: make sure pub is always correct
                fname = 'pub/%s/%s/%s.%s.%s' % (
                    self.organizer.slug, self.slug, fname_base, nonce, s.value.split('.')[-1]
                )
                newname = default_storage.save(fname, fi)
                s.value = 'file://' + newname
                s.save()
            elif s.key == 'tax_rate_default':
                try:
                    if int(s.value) in tax_map:
                        s.value = tax_map.get(int(s.value)).pk
                        s.save()
                except ValueError:
                    pass
            else:
                s.save()

        self.settings.flush()
        event_copy_data.send(
            sender=self, other=other,
            tax_map=tax_map, category_map=category_map, item_map=item_map, variation_map=variation_map,
            question_map=question_map, checkin_list_map=checkin_list_map, quota_map=quota_map,
        )

        if has_custom_style:
            regenerate_css.apply_async(args=(self.pk,))

    def get_payment_providers(self, cached=False) -> dict:
        """
        Returns a dictionary of initialized payment providers mapped by their identifiers.
        """
        from ..signals import register_payment_providers

        if not cached or not hasattr(self, '_cached_payment_providers'):
            responses = register_payment_providers.send(self)
            providers = {}
            for receiver, response in responses:
                if not isinstance(response, list):
                    response = [response]
                for p in response:
                    pp = p(self)
                    providers[pp.identifier] = pp

            self._cached_payment_providers = OrderedDict(sorted(
                providers.items(), key=lambda v: (-v[1].priority, str(v[1].verbose_name))
            ))
        return self._cached_payment_providers

    def get_html_mail_renderer(self):
        """
        Returns the currently selected HTML email renderer
        """
        return self.get_html_mail_renderers()[
            self.settings.mail_html_renderer
        ]

    def get_html_mail_renderers(self) -> dict:
        """
        Returns a dictionary of initialized HTML email renderers mapped by their identifiers.
        """
        from ..signals import register_html_mail_renderers

        responses = register_html_mail_renderers.send(self)
        renderers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                if pp.is_available:
                    renderers[pp.identifier] = pp
        return renderers

    def get_invoice_renderers(self) -> dict:
        """
        Returns a dictionary of initialized invoice renderers mapped by their identifiers.
        """
        from ..signals import register_invoice_renderers

        responses = register_invoice_renderers.send(self)
        renderers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                renderers[pp.identifier] = pp
        return renderers

    @cached_property
    def ticket_secret_generators(self) -> dict:
        """
        Returns a dictionary of cached initialized ticket secret generators mapped by their identifiers.
        """
        from ..signals import register_ticket_secret_generators

        responses = register_ticket_secret_generators.send(self)
        renderers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                renderers[pp.identifier] = pp
        return renderers

    @property
    def ticket_secret_generator(self):
        """
        Returns the currently configured ticket secret generator.
        """
        tsgs = self.ticket_secret_generators
        return tsgs.get(self.settings.ticket_secret_generator, tsgs.get('random'))

    def get_data_shredders(self) -> dict:
        """
        Returns a dictionary of initialized data shredders mapped by their identifiers.
        """
        from ..signals import register_data_shredders

        responses = register_data_shredders.send(self)
        renderers = {}
        for receiver, response in responses:
            if not isinstance(response, list):
                response = [response]
            for p in response:
                pp = p(self)
                renderers[pp.identifier] = pp
        return renderers

    @property
    def invoice_renderer(self):
        """
        Returns the currently configured invoice renderer.
        """
        irs = self.get_invoice_renderers()
        return irs[self.settings.invoice_renderer]

    def subevents_annotated(self, channel, voucher=None):
        return SubEvent.annotated(self.subevents, channel, voucher)

    def subevents_sorted(self, queryset):
        ordering = self.settings.get('frontpage_subevent_ordering', default='date_ascending', as_type=str)
        orderfields = {
            'date_ascending': ('date_from', 'name'),
            'date_descending': ('-date_from', 'name'),
            'name_ascending': ('name', 'date_from'),
            'name_descending': ('-name', 'date_from'),
        }[ordering]
        subevs = queryset.annotate(
            has_paid_item=Value(
                self.cache.get_or_set('has_paid_item', lambda: self.items.filter(default_price__gt=0).exists(), 3600),
                output_field=models.BooleanField()
            )
        ).filter(
            Q(active=True) & Q(is_public=True) & (
                Q(Q(date_to__isnull=True) & Q(date_from__gte=now() - timedelta(hours=24)))
                | Q(date_to__gte=now() - timedelta(hours=24))
            )
        )  # order_by doesn't make sense with I18nField
        if ordering in ("date_ascending", "date_descending"):
            # if primary order is by date, then order in database
            # this allows to limit/slice results
            return subevs.order_by(*orderfields)

        for f in reversed(orderfields):
            if f.startswith('-'):
                subevs = sorted(subevs, key=attrgetter(f[1:]), reverse=True)
            else:
                subevs = sorted(subevs, key=attrgetter(f))
        return subevs

    @property
    def meta_data(self):
        data = {p.name: p.default for p in self.organizer.meta_properties.all()}
        if hasattr(self, 'meta_values_cached'):
            data.update({v.property.name: v.value for v in self.meta_values_cached})
        else:
            data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})

        return OrderedDict((k, v) for k, v in sorted(data.items(), key=lambda k: k[0]))

    @property
    def has_payment_provider(self):
        result = False
        for provider in self.get_payment_providers().values():
            if provider.is_enabled and provider.identifier not in ('free', 'boxoffice', 'offsetting', 'giftcard'):
                result = True
                break
        return result

    @property
    def has_paid_things(self):
        from .items import Item, ItemVariation

        return Item.objects.filter(event=self, default_price__gt=0).exists()\
            or ItemVariation.objects.filter(item__event=self, default_price__gt=0).exists()

    @cached_property
    def live_issues(self):
        from pretix.base.signals import event_live_issues
        issues = []

        if self.has_paid_things and not self.has_payment_provider:
            issues.append(_('You have configured at least one paid product but have not enabled any payment methods.'))

        if not self.quotas.exists():
            issues.append(_('You need to configure at least one quota to sell anything.'))

        for mp in self.organizer.meta_properties.all():
            if mp.required and not self.meta_data.get(mp.name):
                issues.append(
                    ('<a {a_attr}>' + gettext('You need to fill the meta parameter "{property}".') + '</a>').format(
                        property=mp.name,
                        a_attr='href="%s#id_prop-%d-value"' % (
                            reverse('control:event.settings', kwargs={'organizer': self.organizer.slug, 'event': self.slug}),
                            mp.pk
                        )
                    )
                )

        responses = event_live_issues.send(self)
        for receiver, response in sorted(responses, key=lambda r: str(r[0])):
            if response:
                issues.append(response)

        return issues

    def get_users_with_any_permission(self):
        """
        Returns a queryset of users who have any permission to this event.

        :return: Iterable of User
        """
        return self.get_users_with_permission(None)

    def get_users_with_permission(self, permission):
        """
        Returns a queryset of users who have a specific permission to this event.

        :return: Iterable of User
        """
        from .auth import User

        if permission:
            kwargs = {permission: True}
        else:
            kwargs = {}

        team_with_perm = Team.objects.filter(
            members__pk=OuterRef('pk'),
            organizer=self.organizer,
            **kwargs
        ).filter(
            Q(all_events=True) | Q(limit_events__pk=self.pk)
        )

        return User.objects.annotate(twp=Exists(team_with_perm)).filter(twp=True)

    def clean_live(self):
        for issue in self.live_issues:
            if issue:
                raise ValidationError(issue)

    def allow_delete(self):
        return not self.orders.exists() and not self.invoices.exists()

    def delete_sub_objects(self):
        from .checkin import Checkin

        Checkin.all.filter(successful=False, list__event=self).delete()
        self.cartposition_set.filter(addon_to__isnull=False).delete()
        self.cartposition_set.all().delete()
        self.vouchers.all().delete()
        self.items.all().delete()
        self.subevents.all().delete()

    def get_available_plugins(self):
        from pretix.base.plugins import get_all_plugins

        return {
            p.module: p for p in get_all_plugins(self)
            if not p.name.startswith('.') and getattr(p, 'visible', True)
        }

    def set_active_plugins(self, modules, allow_restricted=frozenset()):
        plugins_active = self.get_plugins()
        plugins_available = self.get_available_plugins()

        enable = [m for m in modules if m not in plugins_active and m in plugins_available]

        for module in enable:
            if getattr(plugins_available[module].app, 'restricted', False) and module not in allow_restricted:
                modules.remove(module)
            elif hasattr(plugins_available[module].app, 'installed'):
                getattr(plugins_available[module].app, 'installed')(self)

        self.plugins = ",".join(modules)

    def enable_plugin(self, module, allow_restricted=frozenset()):
        plugins_active = self.get_plugins()
        from pretix.presale.style import regenerate_css

        if module not in plugins_active:
            plugins_active.append(module)
            self.set_active_plugins(plugins_active, allow_restricted=allow_restricted)

        regenerate_css.apply_async(args=(self.pk,))

    def disable_plugin(self, module):
        plugins_active = self.get_plugins()
        from pretix.presale.style import regenerate_css

        if module in plugins_active:
            plugins_active.remove(module)
            self.set_active_plugins(plugins_active)

            plugins_available = self.get_available_plugins()
            if module in plugins_available and hasattr(plugins_available[module].app, 'uninstalled'):
                getattr(plugins_available[module].app, 'uninstalled')(self)

        regenerate_css.apply_async(args=(self.pk,))

    @staticmethod
    def clean_has_subevents(event, has_subevents):
        if event is not None and event.has_subevents is not None:
            if event.has_subevents != has_subevents:
                raise ValidationError(_('Once created an event cannot change between an series and a single event.'))

    @staticmethod
    def clean_slug(organizer, event, slug):
        if event is not None and event.slug is not None:
            if event.slug != slug:
                raise ValidationError(_('The event slug cannot be changed.'))
        else:
            if Event.objects.filter(slug=slug, organizer=organizer).exists():
                raise ValidationError(_('This slug has already been used for a different event.'))

    @staticmethod
    def clean_dates(date_from, date_to):
        if date_from is not None and date_to is not None:
            if date_from > date_to:
                raise ValidationError(_('The event cannot end before it starts.'))

    @staticmethod
    def clean_presale(presale_start, presale_end):
        if presale_start is not None and presale_end is not None:
            if presale_start > presale_end:
                raise ValidationError(_('The event\'s presale cannot end before it starts.'))


class SubEvent(EventMixin, LoggedModel):
    """
    This model represents a date within an event series.

    :param event: The event this belongs to
    :type event: Event
    :param active: Whether to show the subevent
    :type active: bool
    :param is_public: Whether to show the subevent in lists
    :type is_public: bool
    :param name: This event's full title
    :type name: str
    :param date_from: The datetime this event starts
    :type date_from: datetime
    :param date_to: The datetime this event ends
    :type date_to: datetime
    :param presale_start: No tickets will be sold before this date.
    :type presale_start: datetime
    :param presale_end: No tickets will be sold after this date.
    :type presale_end: datetime
    :param location: venue
    :type location: str
    """

    _event_id = 'event_id'
    event = models.ForeignKey(Event, related_name="subevents", on_delete=models.PROTECT)
    active = models.BooleanField(default=False, verbose_name=_("Active"),
                                 help_text=_("Only with this checkbox enabled, this date is visible in the "
                                             "frontend to users."))
    is_public = models.BooleanField(default=True,
                                    verbose_name=_("Show in lists"),
                                    help_text=_("If selected, this event will show up publicly on the list of dates "
                                                "for your event."))
    name = I18nCharField(
        max_length=200,
        verbose_name=_("Name"),
    )
    date_from = models.DateTimeField(verbose_name=_("Event start time"))
    date_to = models.DateTimeField(null=True, blank=True,
                                   verbose_name=_("Event end time"))
    date_admission = models.DateTimeField(null=True, blank=True,
                                          verbose_name=_("Admission time"))
    presale_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("End of presale"),
        help_text=_("Optional. No products will be sold after this date. If you do not set this value, the presale "
                    "will end after the end date of your event."),
    )
    presale_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Start of presale"),
        help_text=_("Optional. No products will be sold before this date."),
    )
    location = I18nTextField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_("Location"),
    )
    geo_lat = models.FloatField(
        verbose_name=_("Latitude"),
        null=True, blank=True,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ]
    )
    geo_lon = models.FloatField(
        verbose_name=_("Longitude"),
        null=True, blank=True,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ]
    )
    frontpage_text = I18nTextField(
        null=True, blank=True,
        verbose_name=_("Frontpage text")
    )
    seating_plan = models.ForeignKey('SeatingPlan', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='subevents', verbose_name=_('Seating plan'))

    items = models.ManyToManyField('Item', through='SubEventItem')
    variations = models.ManyToManyField('ItemVariation', through='SubEventItemVariation')

    last_modified = models.DateTimeField(
        auto_now=True, db_index=True
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Date in event series")
        verbose_name_plural = _("Dates in event series")
        ordering = ("date_from", "name")

    def __str__(self):
        return '{} - {} {}'.format(
            self.name,
            self.get_date_range_display(),
            date_format(self.date_from.astimezone(self.timezone), "TIME_FORMAT") if self.settings.show_times else ""
        ).strip()

    def _seats(self, ignore_voucher=None):
        from .seating import Seat
        qs_annotated = Seat.annotated(self.seats, self.event_id, self,
                                      ignore_voucher_id=ignore_voucher.pk if ignore_voucher else None,
                                      minimal_distance=self.settings.seating_minimal_distance,
                                      distance_only_within_row=self.settings.seating_distance_within_row)
        return qs_annotated

    @classmethod
    def annotated(cls, qs, channel='web', voucher=None):
        from .items import SubEventItem, SubEventItemVariation

        qs = super().annotated(qs, channel, voucher=voucher)
        qs = qs.annotate(
            disabled_items=Coalesce(
                Subquery(
                    SubEventItem.objects.filter(
                        Q(disabled=True) | Q(available_from__gt=now()) | Q(available_until__lt=now()),
                        subevent=OuterRef('pk'),
                    ).order_by().values('subevent').annotate(items=GroupConcat('item_id', delimiter=',')).values('items'),
                    output_field=models.TextField(),
                ),
                Value(''),
                output_field=models.TextField()
            ),
            disabled_vars=Coalesce(
                Subquery(
                    SubEventItemVariation.objects.filter(
                        Q(disabled=True) | Q(available_from__gt=now()) | Q(available_until__lt=now()),
                        subevent=OuterRef('pk'),
                    ).order_by().values('subevent').annotate(items=GroupConcat('variation_id', delimiter=',')).values('items'),
                    output_field=models.TextField(),
                ),
                Value(''),
                output_field=models.TextField()
            )
        )

        return qs

    @cached_property
    def settings(self):
        return self.event.settings

    @cached_property
    def item_overrides(self):
        from .items import SubEventItem

        return {
            si.item_id: si
            for si in SubEventItem.objects.filter(subevent=self)
        }

    @cached_property
    def var_overrides(self):
        from .items import SubEventItemVariation

        return {
            si.variation_id: si
            for si in SubEventItemVariation.objects.filter(subevent=self)
        }

    @property
    def item_price_overrides(self):
        return {
            si.item_id: si.price
            for si in self.item_overrides.values() if si.price is not None
        }

    @property
    def var_price_overrides(self):
        return {
            si.variation_id: si.price
            for si in self.var_overrides.values() if si.price is not None
        }

    @property
    def meta_data(self):
        data = self.event.meta_data
        if hasattr(self, 'meta_values_cached'):
            data.update({v.property.name: v.value for v in self.meta_values_cached})
        else:
            data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})
        return data

    @property
    def currency(self):
        return self.event.currency

    def allow_delete(self):
        return not self.orderposition_set.exists() and not self.transaction_set.exists()

    def delete(self, *args, **kwargs):
        clear_cache = kwargs.pop('clear_cache', False)
        super().delete(*args, **kwargs)
        if self.event and clear_cache:
            self.event.cache.clear()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_dates = (self.date_from, self.date_to)

    def save(self, *args, **kwargs):
        from .orders import Order

        is_new = not bool(self.pk)

        clear_cache = kwargs.pop('clear_cache', False)
        super().save(*args, **kwargs)
        if self.event and clear_cache:
            self.event.cache.clear()

        if not is_new and (self.date_from, self.date_to) != self.__original_dates:
            """
            This is required to guarantee a synchronization invariant of our scanning apps.
            Our syncing apps throw away order records of subevents more than X days ago, since
            they are not interesting for ticket scanning and pose a performance hazard. However,
            the app needs to know when a subevent is moved to a date in the future, since that
            might require it to re-download and re-store the orders.
            """
            Order.objects.filter(all_positions__subevent=self).update(last_modified=now())

    @staticmethod
    def clean_items(event, items):
        for item in items:
            if event != item.event:
                raise ValidationError(_('One or more items do not belong to this event.'))

    @staticmethod
    def clean_variations(event, variations):
        for variation in variations:
            if event != variation.item.event:
                raise ValidationError(_('One or more variations do not belong to this event.'))


@scopes_disabled()
def generate_invite_token():
    return get_random_string(length=32, allowed_chars=string.ascii_lowercase + string.digits)


class EventLock(models.Model):
    event = models.CharField(max_length=36, primary_key=True)
    date = models.DateTimeField(auto_now=True)
    token = models.UUIDField(default=uuid.uuid4)


class EventMetaProperty(LoggedModel):
    """
    An organizer account can have EventMetaProperty objects attached to define meta information fields
    for its events. This information can be re-used for example in ticket layouts.

    :param organizer: The organizer this property is defined for.
    :type organizer: Organizer
    :param name: Name
    :type name: Name of the property, used in various places
    :param default: Default value
    :type default: str
    """
    organizer = models.ForeignKey(Organizer, related_name="meta_properties", on_delete=models.CASCADE)
    name = models.CharField(
        max_length=50, db_index=True,
        help_text=_(
            "Can not contain spaces or special characters except underscores"
        ),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9_]+$",
                message=_("The property name may only contain letters, numbers and underscores."),
            ),
        ],
        verbose_name=_("Name"),
    )
    default = models.TextField(blank=True, verbose_name=_("Default value"))
    protected = models.BooleanField(default=False,
                                    verbose_name=_("Can only be changed by organizer-level administrators"))
    required = models.BooleanField(
        default=False, verbose_name=_("Required for events"),
        help_text=_("If checked, an event can only be taken live if the property is set. In event series, its always "
                    "optional to set a value for individual dates")
    )
    allowed_values = models.TextField(
        null=True, blank=True,
        verbose_name=_("Valid values"),
        help_text=_("If you keep this empty, any value is allowed. Otherwise, enter one possible value per line.")
    )
    filter_allowed = models.BooleanField(
        default=True, verbose_name=_("Can be used for filtering"),
        help_text=_("This field will be shown to filter events or reports in the backend, and it can also be used "
                    "for hidden filter parameters in the frontend (e.g. using the widget).")
    )

    def full_clean(self, exclude=None, validate_unique=True):
        super().full_clean(exclude, validate_unique)
        if self.default and self.required:
            raise ValidationError(_("A property can either be required or have a default value, not both."))
        if self.default and self.allowed_values and self.default not in self.allowed_values.splitlines():
            raise ValidationError(_("You cannot set a default value that is not a valid value."))

    class Meta:
        ordering = ("name",)


class EventMetaValue(LoggedModel):
    """
    A meta-data value assigned to an event.

    :param event: The event this metadata is valid for
    :type event: Event
    :param property: The property this value belongs to
    :type property: EventMetaProperty
    :param value: The actual value
    :type value: str
    """
    event = models.ForeignKey('Event', on_delete=models.CASCADE,
                              related_name='meta_values')
    property = models.ForeignKey('EventMetaProperty', on_delete=models.CASCADE,
                                 related_name='event_values')
    value = models.TextField()

    class Meta:
        unique_together = ('event', 'property')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()


class SubEventMetaValue(LoggedModel):
    """
    A meta-data value assigned to a sub-event.

    :param event: The event this metadata is valid for
    :type event: Event
    :param property: The property this value belongs to
    :type property: EventMetaProperty
    :param value: The actual value
    :type value: str
    """
    subevent = models.ForeignKey('SubEvent', on_delete=models.CASCADE,
                                 related_name='meta_values')
    property = models.ForeignKey('EventMetaProperty', on_delete=models.CASCADE,
                                 related_name='subevent_values')
    value = models.TextField()

    class Meta:
        unique_together = ('subevent', 'property')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()


class EventFooterLink(models.Model):
    """
    A footer link assigned to an event.
    """
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='footer_links')
    label = I18nCharField(
        max_length=200,
        verbose_name=_("Link text"),
    )
    url = models.URLField(
        verbose_name=_("Link URL"),
    )

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.event.cache.clear()
