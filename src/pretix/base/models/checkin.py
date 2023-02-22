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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import (
    Count, Exists, F, Max, OuterRef, Q, Subquery, Value, Window,
)
from django.db.models.expressions import RawSQL
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager, scopes_disabled

from pretix.base.media import MEDIA_TYPES
from pretix.base.models import LoggedModel
from pretix.base.models.fields import MultiStringField
from pretix.helpers import PostgresWindowFrame


class CheckinList(LoggedModel):
    event = models.ForeignKey('Event', related_name='checkin_lists', on_delete=models.CASCADE)
    name = models.CharField(max_length=190)
    all_products = models.BooleanField(default=True, verbose_name=_("All products (including newly created ones)"))
    limit_products = models.ManyToManyField('Item', verbose_name=_("Limit to products"), blank=True)
    subevent = models.ForeignKey('SubEvent', null=True, blank=True,
                                 verbose_name=pgettext_lazy('subevent', 'Date'),
                                 on_delete=models.CASCADE,
                                 help_text=_('If you choose "all dates", tickets will be considered part of this list '
                                             'and valid for check-in regardless of which date they are purchased for. '
                                             'You can limit their validity through the advanced check-in rules, '
                                             'though.'))
    include_pending = models.BooleanField(verbose_name=pgettext_lazy('checkin', 'Include pending orders'),
                                          default=False,
                                          help_text=_('With this option, people will be able to check in even if the '
                                                      'order has not been paid.'))
    addon_match = models.BooleanField(
        verbose_name=_('Allow checking in add-on tickets by scanning the main ticket'),
        default=False,
        help_text=_('A scan will only be possible if the check-in list is configured such that there is always exactly '
                    'one matching add-on ticket. Ambiguous scans will be rejected..')
    )
    gates = models.ManyToManyField(
        'Gate', verbose_name=_("Gates"), blank=True,
        help_text=_("Does not have any effect for the validation of tickets, only for the automatic configuration of "
                    "check-in devices.")
    )
    allow_entry_after_exit = models.BooleanField(
        verbose_name=_('Allow re-entering after an exit scan'),
        default=True
    )
    allow_multiple_entries = models.BooleanField(
        verbose_name=_('Allow multiple entries per ticket'),
        help_text=_('Use this option to turn off warnings if a ticket is scanned a second time.'),
        default=False
    )
    exit_all_at = models.DateTimeField(
        verbose_name=_('Automatically check out everyone at'),
        null=True, blank=True
    )
    auto_checkin_sales_channels = MultiStringField(
        default=[],
        blank=True,
        verbose_name=_('Sales channels to automatically check in'),
        help_text=_('All items on this check-in list will be automatically marked as checked-in when purchased through '
                    'any of the selected sales channels. This option can be useful when tickets sold at the box office '
                    'are not checked again before entry and should be considered validated directly upon purchase.')
    )
    rules = models.JSONField(default=dict, blank=True)

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        ordering = ('subevent__date_from', 'name', 'pk')

    def positions_query(self, ignore_status=False):
        from . import Order, OrderPosition

        qs = OrderPosition.all.filter(
            order__event=self.event,
        )
        if not ignore_status:
            if self.include_pending:
                qs = qs.filter(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING], canceled=False)
            else:
                qs = qs.filter(
                    Q(order__status=Order.STATUS_PAID) |
                    Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True),
                    canceled=False
                )

        if self.subevent_id:
            qs = qs.filter(subevent_id=self.subevent_id)
        if not self.all_products:
            qs = qs.filter(item__in=self.limit_products.values_list('id', flat=True))
        return qs

    @property
    def positions(self):
        return self.positions_query(ignore_status=False)

    @scopes_disabled()
    def positions_inside_query(self, ignore_status=False, at_time=None):
        if at_time is None:
            c_q = []
        else:
            c_q = [Q(datetime__lt=at_time)]

        if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
            # Use a simple approach that works on all databases
            qs = self.positions_query(ignore_status=ignore_status).annotate(
                last_entry=Subquery(
                    Checkin.objects.filter(
                        *c_q,
                        position_id=OuterRef('pk'),
                        list_id=self.pk,
                        type=Checkin.TYPE_ENTRY,
                    ).order_by().values('position_id').annotate(
                        m=Max('datetime')
                    ).values('m')
                ),
                last_exit=Subquery(
                    Checkin.objects.filter(
                        *c_q,
                        position_id=OuterRef('pk'),
                        list_id=self.pk,
                        type=Checkin.TYPE_EXIT,
                    ).order_by().values('position_id').annotate(
                        m=Max('datetime')
                    ).values('m')
                ),
            ).filter(
                Q(last_entry__isnull=False)
                & Q(
                    Q(last_exit__isnull=True) | Q(last_exit__lt=F('last_entry'))
                )
            )
            return qs

        # Use the PostgreSQL-specific query using Window functions, which is a lot faster.
        # On a real-world example with ~100k tickets, of which ~17k are checked in, we observed
        # a speed-up from 29s (old) to a few hundred milliseconds (new)!
        # Why is this so much faster? The regular query get's PostgreSQL all busy with filtering
        # the tickets both by their belonging the event and checkin status at the same time, while
        # this query just iterates over all successful checkins on the list, and -- by the power
        # of window functions -- asks "is this an entry that is followed by no exit?". Then we
        # dedupliate by position and count it up.
        cl = self
        base_q, base_params = (
            Checkin.all.filter(*c_q, successful=True, list=cl)
            .annotate(
                cnt_exists_after=Window(
                    expression=Count("position_id", filter=Q(type=Value("exit"))),
                    partition_by=[F("position_id"), F("list_id")],
                    order_by=F("datetime").asc(),
                    frame=PostgresWindowFrame(
                        "ROWS", start="1 following", end="unbounded following"
                    ),
                )
            )
            .values("position_id", "type", "datetime", "cnt_exists_after")
            .query.sql_with_params()
        )
        return self.positions_query(ignore_status=ignore_status).filter(
            pk__in=RawSQL(
                f"""
                SELECT "position_id"
                FROM ({str(base_q)}) s
                WHERE "type" = %s AND "cnt_exists_after" = 0
                GROUP BY "position_id"
                """,
                [*base_params, Checkin.TYPE_ENTRY]
            )
        )

    @property
    def positions_inside(self):
        return self.positions_inside_query(None)

    @property
    def inside_count(self):
        return self.positions_inside_query(None).count()

    @property
    @scopes_disabled()
    # Disable scopes, because this query is safe and the additional organizer filter in the EXISTS() subquery tricks PostgreSQL into a bad
    # subplan that sequentially scans all events
    def checkin_count(self):
        return self.event.cache.get_or_set(
            'checkin_list_{}_checkin_count'.format(self.pk),
            lambda: self.positions.using(settings.DATABASE_REPLICA).annotate(
                checkedin=Exists(Checkin.objects.filter(list_id=self.pk, position=OuterRef('pk'), type=Checkin.TYPE_ENTRY,))
            ).filter(
                checkedin=True
            ).count(),
            60
        )

    @property
    def percent(self):
        pc = self.position_count
        return round(self.checkin_count * 100 / pc) if pc else 0

    @property
    def position_count(self):
        return self.event.cache.get_or_set(
            'checkin_list_{}_position_count'.format(self.pk),
            lambda: self.positions.count(),
            60
        )

    def touch(self):
        self.event.cache.delete('checkin_list_{}_position_count'.format(self.pk))
        self.event.cache.delete('checkin_list_{}_checkin_count'.format(self.pk))

    @staticmethod
    def annotate_with_numbers(qs, event):
        # This is only kept for backwards-compatibility reasons. This method used to precompute .position_count
        # and .checkin_count through a huge subquery chain, but was dropped for performance reasons.
        return qs

    def __str__(self):
        return self.name

    @classmethod
    def validate_rules(cls, rules, seen_nonbool=False, depth=0):
        # While we implement a full jsonlogic machine on Python-level, we also use the logic rules to generate
        # SQL queries, which is not a full implementation of JSON logic right now, but makes some assumptions,
        # e.g. it does not support something like (a AND b) == (c OR D)
        # Every change to our supported JSON logic must be done
        # * in pretix.base.services.checkin
        # * in pretix.base.models.checkin
        # * in pretix.helpers.jsonlogic_boolalg
        # * in checkinrules.js
        # * in libpretixsync
        # * in pretixscan-ios (in the future)
        top_level_operators = {
            '<', '<=', '>', '>=', '==', '!=', 'inList', 'isBefore', 'isAfter', 'or', 'and'
        }
        allowed_operators = top_level_operators | {
            'buildTime', 'objectList', 'lookup', 'var',
        }
        allowed_vars = {
            'product', 'variation', 'now', 'now_isoweekday', 'entries_number', 'entries_today', 'entries_days',
            'minutes_since_last_entry', 'minutes_since_first_entry',
        }
        if not rules or not isinstance(rules, dict):
            return rules

        if len(rules) > 1:
            raise ValidationError(f'Rules should not include dictionaries with more than one key, found: "{rules}".')

        operator = list(rules.keys())[0]

        if operator not in allowed_operators:
            raise ValidationError(f'Logic operator "{operator}" is currently not allowed.')

        if depth == 0 and operator not in top_level_operators:
            raise ValidationError(f'Logic operator "{operator}" is currently not allowed on the first level.')

        values = rules[operator]
        if not isinstance(values, list) and not isinstance(values, tuple):
            values = [values]

        if operator == 'var':
            if values[0] not in allowed_vars:
                raise ValidationError(f'Logic variable "{values[0]}" is currently not allowed.')
            return rules

        if operator in ('or', 'and') and seen_nonbool:
            raise ValidationError('You cannot use OR/AND logic on a level below a comparison operator.')

        for v in values:
            cls.validate_rules(v, seen_nonbool=seen_nonbool or operator not in ('or', 'and'), depth=depth + 1)

        if operator in ('or', 'and') and depth == 0 and not values:
            return {}

        return rules


class SuccessfulCheckinManager(ScopedManager(organizer='list__event__organizer').__class__):
    def get_queryset(self):
        return super().get_queryset().filter(successful=True)


class Checkin(models.Model):
    """
    A check-in object is created when a ticket is scanned with our scanning apps.
    """
    TYPE_ENTRY = 'entry'
    TYPE_EXIT = 'exit'
    CHECKIN_TYPES = (
        (TYPE_ENTRY, _('Entry')),
        (TYPE_EXIT, _('Exit')),
    )

    REASON_CANCELED = 'canceled'
    REASON_INVALID = 'invalid'
    REASON_UNPAID = 'unpaid'
    REASON_PRODUCT = 'product'
    REASON_RULES = 'rules'
    REASON_REVOKED = 'revoked'
    REASON_INCOMPLETE = 'incomplete'
    REASON_ALREADY_REDEEMED = 'already_redeemed'
    REASON_AMBIGUOUS = 'ambiguous'
    REASON_ERROR = 'error'
    REASON_BLOCKED = 'blocked'
    REASON_INVALID_TIME = 'invalid_time'
    REASONS = (
        (REASON_CANCELED, _('Order canceled')),
        (REASON_INVALID, _('Unknown ticket')),
        (REASON_UNPAID, _('Ticket not paid')),
        (REASON_RULES, _('Forbidden by custom rule')),
        (REASON_REVOKED, _('Ticket code revoked/changed')),
        (REASON_INCOMPLETE, _('Information required')),
        (REASON_ALREADY_REDEEMED, _('Ticket already used')),
        (REASON_PRODUCT, _('Ticket type not allowed here')),
        (REASON_AMBIGUOUS, _('Ticket code is ambiguous on list')),
        (REASON_ERROR, _('Server error')),
        (REASON_BLOCKED, _('Ticket blocked')),
        (REASON_INVALID_TIME, _('Ticket not valid at this time')),
    )

    successful = models.BooleanField(
        default=True,
    )
    error_reason = models.CharField(
        max_length=100,
        choices=REASONS,
        null=True,
        blank=True,
    )
    error_explanation = models.TextField(
        null=True,
        blank=True,
    )

    position = models.ForeignKey(
        'pretixbase.OrderPosition',
        related_name='all_checkins',
        on_delete=models.CASCADE,
        null=True, blank=True,
    )

    # For "raw" scans where we do not know which position they belong to (e.g. scan of signed
    # barcode that is not in database).
    raw_barcode = models.TextField(null=True, blank=True)
    raw_source_type = models.CharField(
        max_length=100,
        null=True, blank=True,
        choices=[(k, v) for k, v in MEDIA_TYPES.items()],
    )
    raw_item = models.ForeignKey(
        'pretixbase.Item',
        related_name='checkins',
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    raw_variation = models.ForeignKey(
        'pretixbase.ItemVariation',
        related_name='checkins',
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    raw_subevent = models.ForeignKey(
        'pretixbase.SubEvent',
        related_name='checkins',
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    # Datetime of checkin, might be different from created if past scans are uploaded
    datetime = models.DateTimeField(default=now)

    # Datetime of creation on server
    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    list = models.ForeignKey(
        'pretixbase.CheckinList', related_name='checkins', on_delete=models.PROTECT,
    )
    type = models.CharField(max_length=100, choices=CHECKIN_TYPES, default=TYPE_ENTRY)

    nonce = models.CharField(max_length=190, null=True, blank=True)

    # Whether or not the scan was made offline
    force_sent = models.BooleanField(default=False, null=True, blank=True)

    # Whether the scan was made offline AND would have not been possible online
    forced = models.BooleanField(default=False)

    device = models.ForeignKey(
        'pretixbase.Device', related_name='checkins', on_delete=models.PROTECT, null=True, blank=True
    )
    gate = models.ForeignKey(
        'pretixbase.Gate', related_name='checkins', on_delete=models.SET_NULL, null=True, blank=True
    )
    auto_checked_in = models.BooleanField(default=False)

    all = ScopedManager(organizer='list__event__organizer')
    objects = SuccessfulCheckinManager()

    class Meta:
        ordering = (('-datetime'),)

    def __repr__(self):
        return "<Checkin: pos {} on list '{}' at {}>".format(
            self.position, self.list, self.datetime
        )

    def save(self, **kwargs):
        super().save(**kwargs)
        if self.position:
            self.position.order.touch()
        self.list.event.cache.delete('checkin_count')
        self.list.touch()

    def delete(self, **kwargs):
        super().delete(**kwargs)
        self.position.order.touch()
        self.list.touch()

    @property
    def is_late_upload(self):
        return self.created and abs(self.created - self.datetime) > timedelta(minutes=2)
