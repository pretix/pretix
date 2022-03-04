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
from itertools import groupby
from typing import Dict, Optional, Tuple

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager

from pretix.base.decimal import round_decimal
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
        null=True,
        blank=True,
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True,
        blank=True,
    )

    subevent_mode = models.CharField(
        verbose_name=_('Event series handling'),
        max_length=50,
        default=SUBEVENT_MODE_MIXED,
        choices=SUBEVENT_MODE_CHOICES,
    )

    condition_all_products = models.BooleanField(
        default=True,
        verbose_name=_("Apply to all products (including newly created ones)")
    )
    condition_limit_products = models.ManyToManyField(
        'Item',
        verbose_name=_("Apply to specific products"),
        blank=True
    )
    condition_apply_to_addons = models.BooleanField(
        default=True,
        verbose_name=_("Apply to add-on products"),
        help_text=_("Discounts never apply to bundled products"),
    )
    condition_min_count = models.PositiveIntegerField(
        verbose_name=_('Minimum number of matching products'),
        default=0,
    )
    condition_min_value = models.DecimalField(
        verbose_name=_('Minimum gross value of matching products'),
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
        help_text=_('Keep the field empty to apply the discount to all matching products.'),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
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

    def apply(self, positions: Dict[int, Tuple[int, Optional[int], Decimal, bool]]) -> Dict[int, Decimal]:
        """
        Tries to apply this discount to a cart

        :param positions: Dictionary mapping IDs to tuples of the form
                          ``(item_id, subevent_id, line_price_gross, is_addon_to)``.
                          Bundled positions may not be included.

        :return: A dictionary mapping keys from the input dictionary to new prices. All positions
                 contained in this dictionary are considered "consumed" and should not be considered
                 by other discounts.
        """
        result = {}

        limit_products = set()
        if not self.condition_all_products:
            limit_products = {p.pk for p in self.condition_limit_products.all()}

        # First, filter out everything not even covered by our product scope
        initial_candidates = [
            idx
            for idx, (item_id, subevent_id, line_price_gross, is_addon_to) in positions.items()
            if (
                (self.condition_all_products or item_id in limit_products) and
                (self.condition_apply_to_addons or not is_addon_to)
            )
        ]

        # Second, if subevent_mode is set, we need to group the cart first
        if self.subevent_mode == self.SUBEVENT_MODE_MIXED:
            # Nothing to do
            candidate_groups = [initial_candidates]

        elif self.subevent_mode == self.SUBEVENT_MODE_SAME:
            # Make groups of positions with the same subevent
            def key(idx):
                return positions[idx][1]  # subevent_id

            _groups = groupby(sorted(initial_candidates, key=key), key=key)
            candidate_groups = [list(g) for k, g in _groups]

        elif self.subevent_mode == self.SUBEVENT_MODE_DISTINCT:
            #
            candidate_groups = []

        for idx_group in candidate_groups:
            if self.condition_min_count and len(idx_group) < self.condition_min_count:
                continue
            if self.condition_min_value and sum(positions[idx][2] for idx in idx_group) < self.condition_min_value:
                continue
            if any(idx in result for idx in idx_group):  # a group overlapping with this group was already used
                continue

            if self.benefit_only_apply_to_cheapest_n_matches:
                idx_group = sorted(idx_group, key=lambda idx: (positions[idx][2], idx))  # sort by line_price

                # Prevent over-consuming of items, i.e. if our discount is "buy 2, get 1 free", we only
                # want to match multiples of 3, at least if we don't violate condition_min_value that way
                for consume_num in range(len(idx_group) // self.condition_min_count * self.condition_min_count, len(idx_group) + 1):
                    if sum(positions[idx][2] for idx in idx_group[:consume_num]) >= self.condition_min_value:
                        consume_idx = idx_group[:consume_num]
                        break
                else:
                    consume_idx = idx_group
                benefit_idx = idx_group[:len(idx_group) // self.condition_min_count]
            else:
                consume_idx = idx_group
                benefit_idx = idx_group

            for idx in benefit_idx:
                previous_price = positions[idx][2]
                new_price = round_decimal(
                    previous_price * (Decimal('100.00') - self.benefit_discount_matching_percent) / Decimal('100.00'),
                    self.event.currency,
                )
                result[idx] = new_price

            for idx in consume_idx:
                result.setdefault(idx, positions[idx][2])

        return result
