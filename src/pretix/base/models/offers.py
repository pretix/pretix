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

import sys
import uuid
from collections import Counter, OrderedDict
from datetime import date, datetime, time
from decimal import Decimal, DecimalException
from typing import Tuple

import dateutil.parser
import pytz
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import formats
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import is_naive, make_aware, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_countries.fields import Country
from django_redis import get_redis_connection
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.models import fields
from pretix.base.models.base import LoggedModel
from pretix.base.models.fields import MultiStringField
from pretix.base.models.tax import TaxedPrice

from .event import Event, SubEvent


class Offer(LoggedModel):
    SUBEVENT_MODE_MIXED = 'mixed'
    SUBEVENT_MODE_SAME = 'same'
    SUBEVENT_MODE_DISTINCT = 'distinct'
    SUBEVENT_MODE_CHOICES = (
        (SUBEVENT_MODE_MIXED, pgettext_lazy('subevent', 'Dates can be mixed without limitation')),
        (SUBEVENT_MODE_SAME, pgettext_lazy('subevent', 'All matching products must be for the same date')),
        (SUBEVENT_MODE_DISTINCT, pgettext_lazy('subevent', 'Each matching product must be for a different date')),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='offers',
    )
    internal_name = models.CharField(
        verbose_name=_("Internal name"),
        help_text=_("If you set this, this will be used instead of the public name in the backend."),
        blank=True, null=True, max_length=255
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )
    sales_channels = fields.MultiStringField(
        verbose_name=_('Sales channels'),
        default=['web'],
        blank=True,
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
        choices=SUBEVENT_MODE_CHOICES,
    )

    condition_all_products = models.BooleanField(default=True, verbose_name=_("All products (including newly created ones)"))
    condition_limit_products = models.ManyToManyField('Item', verbose_name=_("Limit to products"), blank=True)
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
        verbose_name=_('Apply discount to this many of the matching products'),
        null=True, blank=True,
    )

    # more feature ideas:
    # - max_usages_per_order
    # - promote_to_user_if_almost_satisfied
    # - require_customer_account
