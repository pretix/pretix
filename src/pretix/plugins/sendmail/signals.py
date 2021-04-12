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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: FlaviaBastos
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.signals import logentry_display
from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="sendmail_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
        return []
    return [
        {
            'label': _('Send out emails'),
            'url': reverse('plugins:sendmail:send', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:sendmail' and url.url_name == 'send'),
            'icon': 'envelope',
            'children': [
                {
                    'label': _('Send email'),
                    'url': reverse('plugins:sendmail:send', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:sendmail' and url.url_name == 'send'),
                },
                {
                    'label': _('Email history'),
                    'url': reverse('plugins:sendmail:history', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:sendmail' and url.url_name == 'history'),
                },
            ]
        },
    ]


@receiver(signal=logentry_display)
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    plains = {
        'pretix.plugins.sendmail.sent': _('Email was sent'),
        'pretix.plugins.sendmail.order.email.sent': _('The order received a mass email.'),
        'pretix.plugins.sendmail.order.email.sent.attendee': _('A ticket holder of this order received a mass email.'),
    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]
