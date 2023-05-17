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
from django.db import models
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled
from i18nfield.fields import I18nCharField

from pretix.base.models import Customer
from pretix.base.models.base import LoggedModel
from pretix.base.models.organizer import Organizer
from pretix.helpers.names import build_name


class MembershipType(LoggedModel):
    id = models.BigAutoField(primary_key=True)
    organizer = models.ForeignKey(Organizer, related_name='membership_types', on_delete=models.CASCADE)
    name = I18nCharField(
        verbose_name=_('Name'),
    )
    transferable = models.BooleanField(
        verbose_name=_('Membership is transferable'),
        help_text=_('If this is selected, the membership can be used to purchase tickets for multiple persons. If not, '
                    'the attendee name always needs to stay the same.'),
        default=False
    )
    allow_parallel_usage = models.BooleanField(
        verbose_name=_('Parallel usage is allowed'),
        help_text=_('If this is selected, the membership can be used to purchase tickets for events happening at the same time. Note '
                    'that this will only check for an identical start time of the events, not for any overlap between events.'),
        default=False
    )
    max_usages = models.PositiveIntegerField(
        verbose_name=_("Maximum usages"),
        help_text=_("Number of times this membership can be used in a purchase."),
        null=True, blank=True,
    )

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return str(self.name)

    def allow_delete(self):
        return not self.memberships.exists() and not self.granted_by.exists()


class MembershipQuerySet(models.QuerySet):

    @scopes_disabled()  # no scoping of subquery
    def with_usages(self, ignored_order=None):
        from . import Order, OrderPosition

        sq = OrderPosition.all.filter(
            used_membership_id=OuterRef('pk'),
            canceled=False,
        ).exclude(
            order__status=Order.STATUS_CANCELED
        )
        if ignored_order:
            sq = sq.exclude(order__id=ignored_order.pk)
        return self.annotate(
            usages=Coalesce(
                Subquery(
                    sq.order_by().values('used_membership_id').annotate(
                        c=Count('*')
                    ).values('c')
                ),
                Value(0),
            )
        )

    def active(self, ev):
        return self.filter(
            canceled=False,
            date_start__lte=ev.date_from,
            date_end__gte=ev.date_from
        )


class MembershipQuerySetManager(ScopedManager(organizer='customer__organizer').__class__):
    def __init__(self):
        super().__init__()
        self._queryset_class = MembershipQuerySet

    def with_usages(self, ignored_order=None):
        return self.get_queryset().with_usages(ignored_order)

    def active(self, ev):
        return self.get_queryset().active(ev)


class Membership(models.Model):
    id = models.BigAutoField(primary_key=True)
    testmode = models.BooleanField(
        verbose_name=_('Test mode'),
        default=False
    )
    canceled = models.BooleanField(
        verbose_name=_('Canceled'),
        default=False
    )
    customer = models.ForeignKey(
        Customer,
        related_name='memberships',
        on_delete=models.PROTECT
    )
    membership_type = models.ForeignKey(
        MembershipType,
        verbose_name=_('Membership type'),
        related_name='memberships',
        on_delete=models.PROTECT
    )
    granted_in = models.ForeignKey(
        'OrderPosition',
        related_name='granted_memberships',
        on_delete=models.PROTECT,
        null=True, blank=True,
    )
    date_start = models.DateTimeField(
        verbose_name=_('Start date')
    )
    date_end = models.DateTimeField(
        verbose_name=_('End date')
    )
    attendee_name_parts = models.JSONField(default=dict, null=True)

    objects = MembershipQuerySetManager()

    class Meta:
        ordering = "-date_end", "-date_start", "membership_type"

    def __str__(self):
        ds = date_format(self.date_start, 'SHORT_DATE_FORMAT')
        de = date_format(self.date_end, 'SHORT_DATE_FORMAT')
        return f'{self.membership_type.name}: {self.attendee_name} ({ds} – {de})'

    @property
    def attendee_name(self):
        return build_name(self.attendee_name_parts, fallback_scheme=lambda: self.customer.organizer.settings.name_scheme)

    def is_valid(self, ev=None):
        if ev:
            dt = ev.date_from
        else:
            dt = now()

        return not self.canceled and dt >= self.date_start and dt <= self.date_end

    def allow_delete(self):
        return self.testmode and not self.orderposition_set.exists()
