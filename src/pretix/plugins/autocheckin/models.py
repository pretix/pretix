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

from django.db import models
from django.utils.translation import gettext_lazy as _

from pretix.base.models import (
    CheckinList, Event, Item, ItemVariation, LoggedModel, SalesChannel,
)
from pretix.base.models.fields import MultiStringField


class AutoCheckinRule(LoggedModel):
    MODE_PLACED = "placed"
    MODE_PAID = "paid"
    MODE_CHOICES = (
        (MODE_PLACED, _("After order was placed")),
        (MODE_PAID, _("After order was paid")),
    )

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    list = models.ForeignKey(
        CheckinList,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Check-in list"),
        help_text=_(
            "If you keep this empty, all lists that match the purchased product will be used."
        ),
    )

    mode = models.CharField(
        max_length=100,
        choices=MODE_CHOICES,
        default=MODE_PLACED,
    )

    all_sales_channels = models.BooleanField(
        verbose_name=_("All sales channels"),
        default=True,
    )
    limit_sales_channels = models.ManyToManyField(
        SalesChannel,
        verbose_name=_("Sales channels"),
        blank=True,
    )

    all_products = models.BooleanField(
        verbose_name=_("All products and variations"),
        default=True,
    )
    limit_products = models.ManyToManyField(Item, verbose_name=_("Products"), blank=True)
    limit_variations = models.ManyToManyField(
        ItemVariation, blank=True, verbose_name=_("Variations")
    )

    all_payment_methods = models.BooleanField(
        verbose_name=_("All payment methods"),
        default=True,
    )
    limit_payment_methods = MultiStringField(
        verbose_name=_("Only including usage of payment providers"),
        null=True,
        blank=True,
    )
