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
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager

from pretix.base.media import MEDIA_TYPES
from pretix.base.models import LoggedModel
from pretix.base.models.customers import Customer
from pretix.base.models.giftcards import GiftCard
from pretix.base.models.orders import OrderPosition
from pretix.base.models.organizer import Organizer


class ReusableMediumQuerySet(models.QuerySet):

    def active(self):
        return self.filter(
            Q(expires__isnull=True) | Q(expires__gte=now()),
            active=True,
        )


class ReusableMediumQuerySetManager(ScopedManager(organizer='organizer').__class__):
    def __init__(self):
        super().__init__()
        self._queryset_class = ReusableMediumQuerySet

    def active(self):
        return self.get_queryset().active()


class ReusableMedium(LoggedModel):
    id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    organizer = models.ForeignKey(
        Organizer,
        related_name='reusable_media',
        on_delete=models.PROTECT
    )

    type = models.CharField(
        verbose_name=pgettext_lazy('reusable_medium', 'Media type'),
        choices=((k, v) for k, v in MEDIA_TYPES.items()),
        max_length=100,
    )
    identifier = models.CharField(
        max_length=200,
        verbose_name=pgettext_lazy('reusable_medium', 'Identifier'),
    )

    active = models.BooleanField(
        verbose_name=_('Active'),
        default=True
    )
    expires = models.DateTimeField(
        verbose_name=_('Expiration date'),
        null=True, blank=True
    )

    customer = models.ForeignKey(
        Customer,
        null=True, blank=True,
        related_name='reusable_media',
        on_delete=models.SET_NULL,
        verbose_name=_('Customer account'),
    )
    linked_orderposition = models.ForeignKey(
        OrderPosition,
        null=True, blank=True,
        related_name='linked_media',
        on_delete=models.SET_NULL,
        verbose_name=_('Linked ticket'),
    )
    linked_giftcard = models.ForeignKey(
        GiftCard,
        null=True, blank=True,
        related_name='linked_media',
        on_delete=models.SET_NULL,
        verbose_name=_('Linked gift card'),
    )

    info = models.JSONField(
        default=dict
    )
    notes = models.TextField(verbose_name=_('Notes'), null=True, blank=True)

    objects = ReusableMediumQuerySetManager()

    @cached_property
    def media_type(self):
        return MEDIA_TYPES[self.type]

    @property
    def is_expired(self):
        return self.expires and self.expires > now()

    class Meta:
        unique_together = (("identifier", "type", "organizer"),)
        index_together = (("identifier", "type", "organizer"), ("updated", "id"))
        ordering = "identifier", "type", "organizer"


class MediumKeySet(models.Model):
    organizer = models.ForeignKey('Organizer', on_delete=models.CASCADE, related_name='medium_key_sets')
    public_id = models.BigIntegerField(
        unique=True,
    )
    media_type = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    uid_key = models.BinaryField()
    diversification_key = models.BinaryField()

    objects = ScopedManager(organizer='organizer')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organizer", "media_type"],
                condition=Q(active=True),
                name="keyset_unique_active",
            ),
        ]
