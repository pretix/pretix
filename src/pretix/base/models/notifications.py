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
from django.utils.translation import gettext_lazy as _


class NotificationSetting(models.Model):
    """
    Stores that a user wants to get notifications of a certain type via a certain
    method for a certain event. If event is None, the notification shall be sent
    for all events the user has access to.

    :param user: The user to nofify.
    :type user: User
    :param action_type: The type of action to notify for.
    :type action_type: str
    :param event: The event to notify for.
    :type event: Event
    :param method: The method to notify with.
    :type method: str
    :param enabled: Indicates whether the specified notification is enabled. If no
                    event is set, this must always be true. If no event is set, setting
                    this to false is equivalent to deleting the object.
    :type enabled: bool
    """
    CHANNELS = (
        ('mail', _('E-mail')),
    )
    user = models.ForeignKey('User', on_delete=models.CASCADE,
                             related_name='notification_settings')
    action_type = models.CharField(max_length=255)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.CASCADE,
                              related_name='notification_settings')
    method = models.CharField(max_length=255, choices=CHANNELS)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'action_type', 'event', 'method')
