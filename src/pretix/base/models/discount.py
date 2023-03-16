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

from collections import defaultdict
from decimal import Decimal
from itertools import groupby
from typing import Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.timezone import now
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
    active = models.BooleanField(
        verbose_name=_("Active"),
        default=True,
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
    condition_ignore_voucher_discounted = models.BooleanField(
        default=False,
        verbose_name=_("Ignore products discounted by a voucher"),
        help_text=_("If this option is checked, products that already received a discount through a voucher will not "
                    "be considered for this discount. However, products that use a voucher only to e.g. unlock a "
                    "hidden product or gain access to sold-out quota will still receive the discount."),
    )
    condition_min_count = models.PositiveIntegerField(
        verbose_name=_('Minimum number of matching products'),
        default=0,
    )
    condition_min_value = models.DecimalField(
        verbose_name=_('Minimum gross value of matching products'),
        decimal_places=2,
        max_digits=13,
        default=Decimal('0.00'),
    )

    benefit_discount_matching_percent = models.DecimalField(
        verbose_name=_('Percentual discount on matching products'),
        decimal_places=2,
        max_digits=10,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    benefit_only_apply_to_cheapest_n_matches = models.PositiveIntegerField(
        verbose_name=_('Apply discount only to this number of matching products'),
        help_text=_(
            'This option allows you to create discounts of the type "buy X get Y reduced/for free". For example, if '
            'you set "Minimum number of matching products" to four and this value to two, the customer\'s cart will be '
            'split into groups of four tickets and the cheapest two tickets within every group will be discounted. If '
            'you want to grant the discount on all matching products, keep this field empty.'
        ),
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

    @classmethod
    def validate_config(cls, data):
        # We forbid a few combinations of settings, because we don't think they are neccessary and at the same
        # time they introduce edge cases, in which it becomes almost impossible to compute the discount optimally
        # and also very hard to understand for the user what is going on.
        if data.get('condition_min_count') and data.get('condition_min_value'):
            raise ValidationError(
                _('You can either set a minimum number of matching products or a minimum value, not both.')
            )

        if not data.get('condition_min_count') and not data.get('condition_min_value'):
            raise ValidationError(
                _('You need to either set a minimum number of matching products or a minimum value.')
            )

        if data.get('condition_min_value') and data.get('benefit_only_apply_to_cheapest_n_matches'):
            raise ValidationError(
                _('You cannot apply the discount only to some of the matched products if you are matching '
                  'on a minimum value.')
            )

        if data.get('subevent_mode') == cls.SUBEVENT_MODE_DISTINCT and data.get('condition_min_value'):
            raise ValidationError(
                _('You cannot apply the discount only to bookings of different dates if you are matching '
                  'on a minimum value.')
            )

    def allow_delete(self):
        return not self.orderposition_set.exists()

    def clean(self):
        super().clean()
        Discount.validate_config({
            'condition_min_count': self.condition_min_count,
            'condition_min_value': self.condition_min_value,
            'benefit_only_apply_to_cheapest_n_matches': self.benefit_only_apply_to_cheapest_n_matches,
            'subevent_mode': self.subevent_mode,
        })

    def is_available_by_time(self, now_dt=None) -> bool:
        now_dt = now_dt or now()
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True

    def _apply_min_value(self, positions, idx_group, result):
        if self.condition_min_value and sum(positions[idx][2] for idx in idx_group) < self.condition_min_value:
            return

        if self.condition_min_count or self.benefit_only_apply_to_cheapest_n_matches:
            raise ValueError('Validation invariant violated.')

        for idx in idx_group:
            previous_price = positions[idx][2]
            new_price = round_decimal(
                previous_price * (Decimal('100.00') - self.benefit_discount_matching_percent) / Decimal('100.00'),
                self.event.currency,
            )
            result[idx] = new_price

    def _apply_min_count(self, positions, idx_group, result):
        if len(idx_group) < self.condition_min_count:
            return

        if not self.condition_min_count or self.condition_min_value:
            raise ValueError('Validation invariant violated.')

        if self.benefit_only_apply_to_cheapest_n_matches:
            if not self.condition_min_count:
                raise ValueError('Validation invariant violated.')

            idx_group = sorted(idx_group, key=lambda idx: (positions[idx][2], -idx))  # sort by line_price

            # Prevent over-consuming of items, i.e. if our discount is "buy 2, get 1 free", we only
            # want to match multiples of 3
            consume_idx = idx_group[:len(idx_group) // self.condition_min_count * self.condition_min_count]
            benefit_idx = idx_group[:len(idx_group) // self.condition_min_count * self.benefit_only_apply_to_cheapest_n_matches]
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

    def apply(self, positions: Dict[int, Tuple[int, Optional[int], Decimal, bool, Decimal]]) -> Dict[int, Decimal]:
        """
        Tries to apply this discount to a cart

        :param positions: Dictionary mapping IDs to tuples of the form
                          ``(item_id, subevent_id, line_price_gross, is_addon_to, voucher_discount)``.
                          Bundled positions may not be included.

        :return: A dictionary mapping keys from the input dictionary to new prices. All positions
                 contained in this dictionary are considered "consumed" and should not be considered
                 by other discounts.
        """
        result = {}

        if not self.active:
            return result

        limit_products = set()
        if not self.condition_all_products:
            limit_products = {p.pk for p in self.condition_limit_products.all()}

        # First, filter out everything not even covered by our product scope
        initial_candidates = [
            idx
            for idx, (item_id, subevent_id, line_price_gross, is_addon_to, voucher_discount) in positions.items()
            if (
                (self.condition_all_products or item_id in limit_products) and
                (self.condition_apply_to_addons or not is_addon_to) and
                (not self.condition_ignore_voucher_discounted or voucher_discount is None or voucher_discount == Decimal('0.00'))
            )
        ]

        if self.subevent_mode == self.SUBEVENT_MODE_MIXED:  # also applies to non-series events
            if self.condition_min_count:
                self._apply_min_count(positions, initial_candidates, result)
            else:
                self._apply_min_value(positions, initial_candidates, result)

        elif self.subevent_mode == self.SUBEVENT_MODE_SAME:
            def key(idx):
                return positions[idx][1]  # subevent_id

            # Build groups of candidates with the same subevent, then apply our regular algorithm
            # to each group

            _groups = groupby(sorted(initial_candidates, key=key), key=key)
            candidate_groups = [list(g) for k, g in _groups]

            for g in candidate_groups:
                if self.condition_min_count:
                    self._apply_min_count(positions, g, result)
                else:
                    self._apply_min_value(positions, g, result)

        elif self.subevent_mode == self.SUBEVENT_MODE_DISTINCT:
            if self.condition_min_value:
                raise ValueError('Validation invariant violated.')

            # Build optimal groups of candidates with distinct subevents, then apply our regular algorithm
            # to each group. Optimal, in this case, means:
            # - First try to build as many groups of size condition_min_count as possible while trying to
            #   balance out the cheapest products so that they are not all in the same group
            # - Then add remaining positions to existing groups if possible
            candidate_groups = []

            # Build a list of subevent IDs in descending order of frequency
            subevent_to_idx = defaultdict(list)
            for idx, p in positions.items():
                subevent_to_idx[p[1]].append(idx)
            for v in subevent_to_idx.values():
                v.sort(key=lambda idx: positions[idx][2])
            subevent_order = sorted(list(subevent_to_idx.keys()), key=lambda s: len(subevent_to_idx[s]), reverse=True)

            # Build groups of exactly condition_min_count distinct subevents
            current_group = []
            while True:
                # Build a list of candidates, which is a list of all positions belonging to a subevent of the
                # maximum cardinality, where the cardinality of a subevent is defined as the number of tickets
                # for that subevent that are not yet part of any group
                candidates = []
                cardinality = None
                for se, l in subevent_to_idx.items():
                    l = [ll for ll in l if ll in initial_candidates and ll not in current_group]
                    if cardinality and len(l) != cardinality:
                        continue
                    if se not in {positions[idx][1] for idx in current_group}:
                        candidates += l
                        cardinality = len(l)

                if not candidates:
                    break

                # Sort the list by prices, then pick one. For "buy 2 get 1 free" we apply a "pick 1 from the start
                # and 2 from the end" scheme to optimize price distribution among groups
                candidates = sorted(candidates, key=lambda idx: positions[idx][2])
                if len(current_group) < (self.benefit_only_apply_to_cheapest_n_matches or 0):
                    candidate = candidates[0]
                else:
                    candidate = candidates[-1]

                current_group.append(candidate)

                # Only add full groups to the list of groups
                if len(current_group) >= max(self.condition_min_count, 1):
                    candidate_groups.append(current_group)
                    for c in current_group:
                        subevent_to_idx[positions[c][1]].remove(c)
                    current_group = []

            # Distribute "leftovers"
            for se in subevent_order:
                if subevent_to_idx[se]:
                    for group in candidate_groups:
                        if se not in {positions[idx][1] for idx in group}:
                            group.append(subevent_to_idx[se].pop())
                            if not subevent_to_idx[se]:
                                break

            for g in candidate_groups:
                self._apply_min_count(positions, g, result)
        return result
