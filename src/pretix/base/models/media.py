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
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretix.base.media import MEDIA_TYPES
from pretix.base.models.customers import Customer
from pretix.base.models.giftcards import GiftCard
from pretix.base.models.orders import OrderPosition
from pretix.base.models.organizer import Organizer


class PhysicalMediumQuerySet(models.QuerySet):

    def active(self, ev):
        return self.filter(
            active=True,
            expires__gte=now(),
        )


class PhysicalMediumQuerySetManager(ScopedManager(organizer='organizer').__class__):
    def __init__(self):
        super().__init__()
        self._queryset_class = PhysicalMediumQuerySet

    def active(self, ev):
        return self.get_queryset().active(ev)


class PhysicalMedium(models.Model):
    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    organizer = models.ForeignKey(
        Organizer,
        related_name='physical_media',
        on_delete=models.PROTECT
    )

    type = models.CharField(
        max_length=100,
        choices=((k, v) for k, v in MEDIA_TYPES.items()),
    )
    identifier = models.CharField(
        max_length=200,
    )

    active = models.BooleanField(
        verbose_name=_('Active'),
        default=True
    )
    expires = models.DateTimeField(null=True)

    customer = models.ForeignKey(
        Customer,
        related_name='physical_media',
        on_delete=models.SET_NULL
    )
    linked_orderposition = models.OneToOneField(  # TODO: OneToOne or ForeignKey?
        OrderPosition,
        related_name='physical_medium',
        on_delete=models.SET_NULL
    )
    linked_giftcard = models.OneToOneField(  # TODO: OneToOne or ForeignKey?
        GiftCard,
        related_name='physical_medium',
        on_delete=models.SET_NULL
    )

    objects = PhysicalMediumQuerySetManager()

    @cached_property
    def media_type(self):
        return MEDIA_TYPES[self.type]

    class Meta:
        unique_together = (("identifier", "type", "organizer"),)
        index_together = (("identifier", "type", "organizer"),)
        ordering = "identifier", "type", "organizer"
