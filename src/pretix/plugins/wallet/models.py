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

from pretix.base.models import LoggedModel
from django_scopes import ScopedManager
from django.core.exceptions import ValidationError


class WalletLayout(LoggedModel):
    event = models.ForeignKey(
        'pretixbase.Event',
        on_delete=models.CASCADE,
        related_name='wallet_layouts'
    )
    name = models.CharField(
        max_length=190,
        verbose_name=_('Name')
    )

    objects = ScopedManager(organizer='event__organizer')


class WalletPlatformLayout(LoggedModel):
    parent = models.ForeignKey(WalletLayout, on_delete=models.CASCADE, related_name="platform_layouts")

    platform = models.CharField(max_length=10)
    style = models.CharField(max_length=255)
    layout = models.JSONField(default=dict)

    objects = ScopedManager(organizer='parent__event__organizer')

    class Meta:
        unique_together = (('parent', 'platform'),)


class WalletLayoutItem(models.Model):
    item = models.ForeignKey('pretixbase.Item', null=True, blank=True, related_name='walletlayout_assignments',
                             on_delete=models.CASCADE)
    layout = models.ForeignKey(WalletLayout, on_delete=models.CASCADE, related_name='item_assignments')

    class Meta:
        unique_together = (('item', 'layout'),)

    def clean(self):
        if self.item.event != self.layout.event:
            raise ValidationError("cannot bind layout to item of different event")
