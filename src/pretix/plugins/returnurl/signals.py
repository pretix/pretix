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
from urllib.parse import urlencode

from django.contrib.messages import constants as messages, get_messages
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _

from pretix.control.signals import nav_event_settings
from pretix.presale.signals import process_request


@receiver(process_request, dispatch_uid="returnurl_process_request")
def returnurl_process_request(sender, request, **kwargs):
    try:
        r = resolve(request.path_info)
    except:
        return

    urlname = r.url_name
    urlkwargs = r.kwargs

    if urlname.startswith('event.order'):
        key = 'order_{}_{}_{}_return_url'.format(urlkwargs.get('organizer', '-'), urlkwargs.get('event', '-'),
                                                 urlkwargs['order'])
        if urlname == 'event.order' and key in request.session:
            url = request.session.get(key)

            query = []
            storage = get_messages(request)
            for message in storage:
                if message.level == messages.ERROR:
                    query.append(('error', str(message)))
                elif message.level == messages.WARNING:
                    query.append(('warning', str(message)))
                if message.level == messages.INFO:
                    query.append(('info', str(message)))
                if message.level == messages.SUCCESS:
                    query.append(('success', str(message)))
            if query:
                if '?' in url:
                    url += '&' + urlencode(query)
                else:
                    url += '?' + urlencode(query)
            r = redirect(url)
            del request.session[key]
            return r
        elif urlname != 'event.order' and 'return_url' in request.GET:
            u = request.GET.get('return_url')
            if not sender.settings.returnurl_prefix:
                raise PermissionDenied('No return URL prefix set.')
            elif not u.startswith(sender.settings.returnurl_prefix):
                raise PermissionDenied('Invalid return URL.')
            request.session[key] = u


@receiver(nav_event_settings, dispatch_uid='returnurl_nav')
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_event_settings',
                                             request=request):
        return []
    return [{
        'label': _('Redirection'),
        'url': reverse('plugins:returnurl:settings', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
        }),
        'active': url.namespace == 'plugins:returnurl',
    }]
