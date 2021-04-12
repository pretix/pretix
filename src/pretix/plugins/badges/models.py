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
import string

from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from pretix.base.models import LoggedModel


def bg_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'pub/{org}/{ev}/badges/{id}-{secret}.pdf'.format(
        org=instance.event.organizer.slug,
        ev=instance.event.slug,
        id=instance.pk,
        secret=secret
    )


class BadgeLayout(LoggedModel):
    event = models.ForeignKey(
        'pretixbase.Event',
        on_delete=models.CASCADE,
        related_name='badge_layouts'
    )
    default = models.BooleanField(
        verbose_name=_('Default'),
        default=False,
    )
    name = models.CharField(
        max_length=190,
        verbose_name=_('Name')
    )
    layout = models.TextField(
        default='[{"type":"textarea","left":"13.09","bottom":"49.73","fontsize":"23.6","color":[0,0,0,1],'
                '"fontfamily":"Open Sans","bold":true,"italic":false,"width":"121.83","content":"attendee_name",'
                '"text":"Max Mustermann","align":"center"}]'
    )
    background = models.FileField(null=True, blank=True, upload_to=bg_name, max_length=255)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class BadgeItem(models.Model):
    # If no BadgeItem exists => use default
    # If BadgeItem exists with layout=None => don't print
    item = models.OneToOneField('pretixbase.Item', null=True, blank=True, related_name='badge_assignment',
                                on_delete=models.CASCADE)
    layout = models.ForeignKey('BadgeLayout', on_delete=models.CASCADE, related_name='item_assignments',
                               null=True, blank=True)

    class Meta:
        ordering = ('id',)
