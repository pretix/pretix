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
from django.dispatch import receiver
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid='webcheckin_nav_event')
def navbar_entry(sender, request, **kwargs):
    url = request.resolver_match
    if not request.user.has_event_permission(request.organizer, request.event, ('can_change_orders', 'can_checkin_orders'), request=request):
        return []
    return [{
        'label': mark_safe(_('Web Check-in') + ' <span class="label label-success">beta</span>'),
        'url': reverse('plugins:webcheckin:index', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
        }),
        'parent': reverse('control:event.orders.checkinlists', kwargs={
            'event': request.event.slug,
            'organizer': request.event.organizer.slug,
        }),
        'external': True,
        'icon': 'check-square-o',
        'active': url.namespace == 'plugins:webcheckin' and url.url_name.startswith('index'),
    }]
