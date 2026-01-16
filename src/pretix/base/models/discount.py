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

from collections import defaultdict, namedtuple
from decimal import Decimal
from itertools import groupby
from math import ceil, inf
from typing import Dict

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager

from pretix.base.decimal import round_decimal
from pretix.base.models.base import LoggedModel

PositionInfo = namedtuple('PositionInfo',
                          ['item_id', 'subevent_id', 'subevent_date_from', 'line_price_gross', 'addon_to',
                           'voucher_discount'])


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
    all_sales_channels = models.BooleanField(
        verbose_name=_("All supported sales channels"),
        default=True,
    )
    limit_sales_channels = models.ManyToManyField(
        "SalesChannel",
        verbose_name=_("Sales channels"),
        blank=True,
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
        verbose_name=_("Count add-on products"),
        help_text=_("Discounts never apply to bundled products"),
    )
    condition_ignore_voucher_discounted = models.BooleanField(
        default=False,
        verbose_name=_("Ignore products discounted by a voucher"),
        help_text=_("If this option is checked, products that already received a discount through a voucher will not "
                    "be considered for this discount. However, products that use a voucher only to e.g. unlock a "
                    "hidden product or gain access to sold-out quota will still be considered."),
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

    benefit_same_products = models.BooleanField(
        default=True,
        verbose_name=_("Apply discount to same set of products"),
        help_text=_("By default, the discount is applied across the same selection of products than the condition for "
                    "the discount given above. If you want, you can however also select a different selection of "
                    "products.")
    )
    benefit_limit_products = models.ManyToManyField(
        'Item',
        verbose_name=_("Apply discount to specific products"),
        related_name='benefit_discounts',
        blank=True
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
    benefit_apply_to_addons = models.BooleanField(
        default=True,
        verbose_name=_("Apply to add-on products"),
        help_text=_("Discounts never apply to bundled products"),
    )
    benefit_ignore_voucher_discounted = models.BooleanField(
        default=False,
        verbose_name=_("Ignore products discounted by a voucher"),
        help_text=_("If this option is checked, products that already received a discount through a voucher will not "
                    "be discounted. However, products that use a voucher only to e.g. unlock a hidden product or gain "
                    "access to sold-out quota will still receive the discount."),
    )

    subevent_date_from = models.DateTimeField(
        verbose_name=pgettext_lazy("subevent", "Available for dates starting from"),
        null=True,
        blank=True,
    )
    subevent_date_until = models.DateTimeField(
        verbose_name=pgettext_lazy("subevent", "Available for dates starting until"),
        null=True,
        blank=True,
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

        if data.get('subevent_mode') == cls.SUBEVENT_MODE_DISTINCT and not data.get('benefit_same_products'):
            raise ValidationError(
                {'benefit_same_products': [
                    _('You cannot apply the discount to a different set of products if the discount is only valid '
                      'for bookings of different dates.')
                ]}
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
            'benefit_same_products': self.benefit_same_products,
        })

    def is_available_by_time(self, now_dt=None) -> bool:
        now_dt = now_dt or now()
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True

    def _apply_min_value(self, positions, condition_idx_group, benefit_idx_group, result, collect_potential_discounts, subevent_id):
        if self.condition_min_value and sum(positions[idx].line_price_gross for idx in condition_idx_group) < self.condition_min_value:
            return

        if self.condition_min_count or self.benefit_only_apply_to_cheapest_n_matches:
            raise ValueError('Validation invariant violated.')

        for idx in benefit_idx_group:
            previous_price = positions[idx].line_price_gross
            new_price = round_decimal(
                previous_price * (Decimal('100.00') - self.benefit_discount_matching_percent) / Decimal('100.00'),
                self.event.currency,
            )
            result[idx] = new_price

        if collect_potential_discounts is not None:
            for idx in condition_idx_group:
                collect_potential_discounts[idx] = [(self, inf, -1, subevent_id)]

    def _addon_idx(self, positions, idx):
        """
        If we have the following cart:

        - Main product
          - 10x Addon product 5€
        - Main product
          - 10x Addon product 5€

        And we have a discount rule that grants "every 10th product is free", people tend to expect

        - Main product
          - 9x Addon product 5€
          - 1x Addon product free
        - Main product
          - 9x Addon product 5€
          - 1x Addon product free

        And get confused if they get

        - Main product
          - 8x Addon product 5€
          - 2x Addon product free
        - Main product
          - 10x Addon product 5€

        Even if the result is the same. Therefore, we sort positions in the cart not only by price, but also by their
        relative index within their addon group. This is only a heuristic and there are *still* scenarios where the more
        unexpected version happens, e.g. if prices are different. We need to accept this as long as discounts work on
        cart level and not on addon-group level, but this simple sorting reduces the number of support issues by making
        the weird case less likely.
        """
        if not positions[idx].addon_to:
            return 0
        return len([1 for i, p in positions.items() if i < idx and p.addon_to == positions[idx].addon_to])

    def _apply_min_count(self, positions, condition_idx_group, benefit_idx_group, result, collect_potential_discounts, subevent_id):
        if len(condition_idx_group) < self.condition_min_count:
            return

        if not self.condition_min_count or self.condition_min_value:
            raise ValueError('Validation invariant violated.')

        if self.benefit_only_apply_to_cheapest_n_matches:
            # sort by line_price
            condition_idx_group = sorted(condition_idx_group, key=lambda idx: (positions[idx].line_price_gross, self._addon_idx(positions, idx), -idx))
            benefit_idx_group = sorted(benefit_idx_group, key=lambda idx: (positions[idx].line_price_gross, self._addon_idx(positions, idx), -idx))

            # Prevent over-consuming of items, i.e. if our discount is "buy 2, get 1 free", we only
            # want to match multiples of 3

            # how many discount applications are allowed according to condition products in cart
            possible_applications_cond = len(condition_idx_group) // self.condition_min_count

            # how many discount applications are possible according to benefitting products in cart
            possible_applications_benefit = ceil(len(benefit_idx_group) / self.benefit_only_apply_to_cheapest_n_matches)

            n_groups = min(possible_applications_cond, possible_applications_benefit)
            consume_idx = condition_idx_group[:n_groups * self.condition_min_count]
            benefit_idx = benefit_idx_group[:n_groups * self.benefit_only_apply_to_cheapest_n_matches]

            if collect_potential_discounts is not None:
                if n_groups * self.benefit_only_apply_to_cheapest_n_matches > len(benefit_idx_group):
                    # partially used discount ("for each 1 ticket you buy, get 50% on 2 t-shirts", cart content: 1 ticket
                    # but only 1 t-shirt) -> 1 shirt definitiv potential discount
                    for idx in consume_idx:
                        collect_potential_discounts[idx] = [
                            (self, n_groups * self.benefit_only_apply_to_cheapest_n_matches - len(benefit_idx_group), -1, subevent_id)
                        ]

                if possible_applications_cond * self.benefit_only_apply_to_cheapest_n_matches > len(benefit_idx_group):
                    # unused discount ("for each 1 ticket you buy, get 50% on 2 t-shirts", cart content: 1 ticket
                    # but 0 t-shirts) -> 2 shirt maybe potential discount (if the 1 ticket is not consumed by a later discount)
                    for i, idx in enumerate(condition_idx_group[
                                            n_groups * self.condition_min_count:
                                            possible_applications_cond * self.condition_min_count
                                            ]):
                        collect_potential_discounts[idx] += [
                            (self, self.benefit_only_apply_to_cheapest_n_matches, i // self.condition_min_count, subevent_id)
                        ]

        else:
            consume_idx = condition_idx_group
            benefit_idx = benefit_idx_group

            if collect_potential_discounts is not None:
                for idx in consume_idx:
                    collect_potential_discounts[idx] = [(self, inf, -1, subevent_id)]

        for idx in benefit_idx:
            previous_price = positions[idx].line_price_gross
            new_price = round_decimal(
                previous_price * (Decimal('100.00') - self.benefit_discount_matching_percent) / Decimal('100.00'),
                self.event.currency,
            )
            result[idx] = new_price

        for idx in consume_idx:
            result.setdefault(idx, positions[idx].line_price_gross)

    def apply(self, positions: Dict[int, PositionInfo],
              collect_potential_discounts=None) -> Dict[int, Decimal]:
        """
        Tries to apply this discount to a cart

        :param positions: Dictionary mapping IDs to PositionInfo tuples.
                          Bundled positions may not be included.
        :param collect_potential_discounts: For detailed description, see pretix.base.services.pricing.apply_discounts

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
        condition_candidates = [
            idx
            for idx, (item_id, subevent_id, subevent_date_from, line_price_gross, is_addon_to, voucher_discount) in
            positions.items()
            if (
                (self.condition_all_products or item_id in limit_products) and
                (self.condition_apply_to_addons or not is_addon_to) and
                (not self.condition_ignore_voucher_discounted or voucher_discount is None or voucher_discount == Decimal('0.00'))
                and (not subevent_id or (
                    self.subevent_date_from is None or subevent_date_from >= self.subevent_date_from)) and (
                        self.subevent_date_until is None or subevent_date_from <= self.subevent_date_until)
            )
        ]

        if self.benefit_same_products:
            benefit_candidates = list(condition_candidates)
        else:
            benefit_products = {p.pk for p in self.benefit_limit_products.all()}
            benefit_candidates = [
                idx
                for idx, (item_id, subevent_id, subevent_date_from, line_price_gross, is_addon_to, voucher_discount) in
                positions.items()
                if (
                    item_id in benefit_products and
                    (self.benefit_apply_to_addons or not is_addon_to) and
                    (not self.benefit_ignore_voucher_discounted or voucher_discount is None or voucher_discount == Decimal('0.00'))
                )
            ]

        if self.subevent_mode == self.SUBEVENT_MODE_MIXED:  # also applies to non-series events
            if self.condition_min_count:
                self._apply_min_count(positions, condition_candidates, benefit_candidates, result, collect_potential_discounts, None)
            else:
                self._apply_min_value(positions, condition_candidates, benefit_candidates, result, collect_potential_discounts, None)

        elif self.subevent_mode == self.SUBEVENT_MODE_SAME:
            def key(idx):
                return positions[idx].subevent_id or 0

            # Build groups of candidates with the same subevent, then apply our regular algorithm
            # to each group

            _groups = groupby(sorted(condition_candidates, key=key), key=key)
            candidate_groups = [(k, list(g)) for k, g in _groups]

            for subevent_id, g in candidate_groups:
                benefit_g = [idx for idx in benefit_candidates if positions[idx].subevent_id == subevent_id]
                if self.condition_min_count:
                    self._apply_min_count(positions, g, benefit_g, result, collect_potential_discounts, subevent_id)
                else:
                    self._apply_min_value(positions, g, benefit_g, result, collect_potential_discounts, subevent_id)

        elif self.subevent_mode == self.SUBEVENT_MODE_DISTINCT:
            if self.condition_min_value or not self.benefit_same_products:
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
                subevent_to_idx[p.subevent_id].append(idx)
            for v in subevent_to_idx.values():
                v.sort(key=lambda idx: (positions[idx].line_price_gross, self._addon_idx(positions, idx)))
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
                    l = [ll for ll in l if ll in condition_candidates and ll not in current_group]
                    if cardinality and len(l) != cardinality:
                        continue
                    if se not in {positions[idx].subevent_id for idx in current_group}:
                        candidates += l
                        cardinality = len(l)

                if not candidates:
                    break

                # Sort the list by prices, then pick one. For "buy 2 get 1 free" we apply a "pick 1 from the start
                # and 2 from the end" scheme to optimize price distribution among groups
                candidates = sorted(candidates, key=lambda idx: (positions[idx].line_price_gross, self._addon_idx(positions, idx)))
                if len(current_group) < (self.benefit_only_apply_to_cheapest_n_matches or 0):
                    candidate = candidates[0]
                else:
                    candidate = candidates[-1]

                current_group.append(candidate)

                # Only add full groups to the list of groups
                if len(current_group) >= max(self.condition_min_count, 1):
                    candidate_groups.append(current_group)
                    for c in current_group:
                        subevent_to_idx[positions[c].subevent_id].remove(c)
                    current_group = []

            # Distribute "leftovers"
            for se in subevent_order:
                if subevent_to_idx[se]:
                    for group in candidate_groups:
                        if se not in {positions[idx].subevent_id for idx in group}:
                            group.append(subevent_to_idx[se].pop())
                            if not subevent_to_idx[se]:
                                break

            for g in candidate_groups:
                self._apply_min_count(
                    positions,
                    [idx for idx in g if idx in condition_candidates],
                    [idx for idx in g if idx in benefit_candidates],
                    result,
                    None,
                    None
                )
        return result
