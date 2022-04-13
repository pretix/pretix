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

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager

from pretix.base.models import fields
from pretix.base.models.base import LoggedModel


class Discount(LoggedModel):
    SUBEVENT_MODE_MIXED = 'mixed'
    SUBEVENT_MODE_SAME = 'same'
    SUBEVENT_MODE_DISTINCT = 'distinct'
    SUBEVENT_MODE_CHOICES = (
        (SUBEVENT_MODE_MIXED, pgettext_lazy('subevent', 'Dates can be mixed without limitation')),
        (SUBEVENT_MODE_SAME, pgettext_lazy('subevent', 'All matching products must be for the same date')),
        (SUBEVENT_MODE_DISTINCT, pgettext_lazy('subevent', 'Each matching product must be for a different date')),
    )

    event = models.ForeignKey(
        'Event',
        on_delete=models.CASCADE,
        related_name='discounts',
    )
    internal_name = models.CharField(
        verbose_name=_("Internal name"),
        max_length=255
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )
    sales_channels = fields.MultiStringField(
        verbose_name=_('Sales channels'),
        default=['web'],
        blank=False,
    )

    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
    )

    subevent_mode = models.CharField(
        verbose_name=_('Event series handling'),
        max_length=50,
        default=SUBEVENT_MODE_MIXED,
        choices=SUBEVENT_MODE_CHOICES,
    )

    condition_all_products = models.BooleanField(default=True, verbose_name=_("Apply to all products (including newly created ones)"))
    condition_limit_products = models.ManyToManyField('Item', verbose_name=_("Apply to specific products"), blank=True)
    condition_min_count = models.PositiveIntegerField(
        verbose_name=_('Minimum number of matching products'),
        default=0,
    )
    condition_min_value = models.DecimalField(
        verbose_name=_('Minimum value of matching products'),
        decimal_places=2,
        max_digits=10,
        default=Decimal('0.00'),
    )

    benefit_discount_matching_percent = models.DecimalField(
        verbose_name=_('Percentual discount on matching products'),
        decimal_places=2,
        max_digits=10,
        default=Decimal('0.00'),
    )
    benefit_only_apply_to_cheapest_n_matches = models.PositiveIntegerField(
        verbose_name=_('Apply discount only to this number of matching products'),
        null=True, blank=True,
    )

    # more feature ideas:
    # - max_usages_per_order
    # - promote_to_user_if_almost_satisfied
    # - require_customer_account

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        ordering = ('position', 'id')

    def __str__(self):
        return self.internal_name

    @property
    def sortkey(self):
        return self.position, self.id

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey
