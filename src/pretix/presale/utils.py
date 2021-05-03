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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import warnings
from importlib import import_module
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import resolve
from django.utils.crypto import constant_time_compare
from django.utils.functional import SimpleLazyObject
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.defaults import permission_denied
from django_scopes import scope

from pretix.base.middleware import LocaleMiddleware
from pretix.base.models import Customer, Event, Organizer
from pretix.multidomain.urlreverse import (
    get_event_domain, get_organizer_domain,
)
from pretix.presale.signals import process_request, process_response

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


def get_customer(request):
    if not hasattr(request, '_cached_customer'):
        session_key = f'customer_auth_id:{request.organizer.pk}'
        hash_session_key = f'customer_auth_hash:{request.organizer.pk}'

        with scope(organizer=request.organizer):
            try:
                customer = request.organizer.customers.get(pk=request.session[session_key])
            except (Customer.DoesNotExist, KeyError):
                request._cached_customer = None
            else:
                session_hash = request.session.get(hash_session_key)
                session_hash_verified = session_hash and constant_time_compare(
                    session_hash,
                    customer.get_session_auth_hash()
                )
                if session_hash_verified:
                    request._cached_customer = customer
                else:
                    request.session.flush()
                    request._cached_customer = None

    return request._cached_customer


def add_customer_to_request(request):
    request.customer = SimpleLazyObject(lambda: get_customer(request))


def customer_login(request, customer):
    session_key = f'customer_auth_id:{request.organizer.pk}'
    hash_session_key = f'customer_auth_hash:{request.organizer.pk}'
    session_auth_hash = customer.get_session_auth_hash()

    if session_key in request.session:
        if request.session[session_key] != customer.pk or (
                not constant_time_compare(request.session.get(hash_session_key, ''), session_auth_hash)):
            # To avoid reusing another user's session, create a new, empty
            # session if the existing session corresponds to a different
            # authenticated user.
            request.session.flush()
    else:
        request.session.cycle_key()

    request.session[session_key] = customer.pk
    request.session[hash_session_key] = session_auth_hash
    request.customer = customer

    customer.last_login = now()
    customer.save(update_fields=['last_login'])

    rotate_token(request)


def customer_logout(request):
    # session_key = f'customer_auth_id:{request.organizer.pk}'
    # hash_session_key = f'customer_auth_hash:{request.organizer.pk}'
    # request.session.pop(session_key, None)
    # request.session.pop(hash_session_key, None)
    # request.session.cycle_key()

    # Instead of only logging out for this organizer, log the user out domain-wide including all carts. This might
    # be expected or unepxected behaviour for the users – we'll need to figure that out in practice.
    request.session.flush()
    rotate_token(request)
    request.customer = None
    request._cached_customer = None


@scope(organizer=None)
def _detect_event(request, require_live=True, require_plugin=None):

    if hasattr(request, '_event_detected'):
        return

    db = 'default'
    if request.method == 'GET':
        db = settings.DATABASE_REPLICA

    url = resolve(request.path_info)

    try:
        if hasattr(request, 'event_domain'):
            # We are on an event's custom domain
            pass
        elif hasattr(request, 'organizer_domain'):
            # We are on an organizer's custom domain
            if 'organizer' in url.kwargs and url.kwargs['organizer']:
                if url.kwargs['organizer'] != request.organizer.slug:
                    raise Http404(_('The selected event was not found.'))
                path = "/" + request.get_full_path().split("/", 2)[-1]
                return redirect(path)

            request.event = request.organizer.events.using(db).get(
                slug=url.kwargs['event'],
                organizer=request.organizer,
            )
            request.organizer = request.organizer

            # If this event has a custom domain, send the user there
            domain = get_event_domain(request.event)
            if domain:
                if request.port and request.port not in (80, 443):
                    domain = '%s:%d' % (domain, request.port)
                path = request.get_full_path().split("/", 2)[-1]
                r = redirect(urljoin('%s://%s' % (request.scheme, domain), path))
                r['Access-Control-Allow-Origin'] = '*'
                return r
        else:
            # We are on our main domain
            if 'event' in url.kwargs and 'organizer' in url.kwargs:
                request.event = Event.objects\
                    .select_related('organizer')\
                    .using(db)\
                    .get(
                        slug=url.kwargs['event'],
                        organizer__slug=url.kwargs['organizer']
                    )
                request.organizer = request.event.organizer

                # If this event has a custom domain, send the user there
                domain = get_event_domain(request.event)
                if domain:
                    if request.port and request.port not in (80, 443):
                        domain = '%s:%d' % (domain, request.port)
                    path = request.get_full_path().split("/", 3)[-1]
                    r = redirect(urljoin('%s://%s' % (request.scheme, domain), path))
                    r['Access-Control-Allow-Origin'] = '*'
                    return r
            elif 'organizer' in url.kwargs:
                request.organizer = Organizer.objects.using(db).get(
                    slug=url.kwargs['organizer']
                )
            else:
                raise Http404()

            # If this organizer has a custom domain, send the user there
            domain = get_organizer_domain(request.organizer)
            if domain:
                if request.port and request.port not in (80, 443):
                    domain = '%s:%d' % (domain, request.port)
                path = request.get_full_path().split("/", 2)[-1]
                r = redirect(urljoin('%s://%s' % (request.scheme, domain), path))
                r['Access-Control-Allow-Origin'] = '*'
                return r

        if not hasattr(request, 'customer'):
            add_customer_to_request(request)

        if hasattr(request, 'event'):
            # Restrict locales to the ones available for this event
            LocaleMiddleware().process_request(request)

            if require_live and not request.event.live:
                can_access = (
                    url.url_name == 'event.auth'
                    or (
                        request.user.is_authenticated
                        and request.user.has_event_permission(request.organizer, request.event, request=request)
                    )

                )
                if not can_access and 'pretix_event_access_{}'.format(request.event.pk) in request.session:
                    sparent = SessionStore(request.session.get('pretix_event_access_{}'.format(request.event.pk)))
                    try:
                        parentdata = sparent.load()
                    except:
                        pass
                    else:
                        can_access = 'event_access' in parentdata

                if not can_access:
                    # Directly construct view instead of just calling `raise` since this case is so common that we
                    # don't want it to show in our log files.
                    return permission_denied(
                        request, PermissionDenied(_('The selected ticket shop is currently not available.'))
                    )

            if require_plugin:
                is_core = any(require_plugin.startswith(m) for m in settings.CORE_MODULES)
                if require_plugin not in request.event.get_plugins() and not is_core:
                    raise Http404(_('This feature is not enabled.'))

            for receiver, response in process_request.send(request.event, request=request):
                if response:
                    return response
        elif hasattr(request, 'organizer'):
            # Restrict locales to the ones available for this organizer
            LocaleMiddleware().process_request(request)

    except Event.DoesNotExist:
        try:
            if hasattr(request, 'organizer_domain'):
                event = request.organizer.events.get(
                    slug__iexact=url.kwargs['event'],
                    organizer=request.organizer,
                )
                pathparts = request.get_full_path().split('/')
                pathparts[1] = event.slug
                return redirect('/'.join(pathparts))
            else:
                if 'event' in url.kwargs and 'organizer' in url.kwargs:
                    event = Event.objects.select_related('organizer').get(
                        slug__iexact=url.kwargs['event'],
                        organizer__slug__iexact=url.kwargs['organizer']
                    )
                    pathparts = request.get_full_path().split('/')
                    pathparts[1] = event.organizer.slug
                    pathparts[2] = event.slug
                    return redirect('/'.join(pathparts))
        except Event.DoesNotExist:
            raise Http404(_('The selected event was not found.'))
        raise Http404(_('The selected event was not found.'))
    except Organizer.DoesNotExist:
        if 'organizer' in url.kwargs:
            try:
                organizer = Organizer.objects.get(
                    slug__iexact=url.kwargs['organizer']
                )
            except Organizer.DoesNotExist:
                raise Http404(_('The selected organizer was not found.'))
            pathparts = request.get_full_path().split('/')
            pathparts[1] = organizer.slug
            return redirect('/'.join(pathparts))
        raise Http404(_('The selected organizer was not found.'))

    request._event_detected = True


def _event_view(function=None, require_live=True, require_plugin=None):
    def event_view_wrapper(func, require_live=require_live):
        def wrap(request, *args, **kwargs):
            ret = _detect_event(request, require_live=require_live, require_plugin=require_plugin)
            if ret:
                return ret
            else:
                with scope(organizer=getattr(request, 'organizer', None)):
                    response = func(request=request, *args, **kwargs)
                    for receiver, r in process_response.send(request.event, request=request, response=response):
                        response = r

                    if isinstance(response, TemplateResponse):
                        response = response.render()

                    return response

        for attrname in dir(func):
            # Preserve flags like csrf_exempt
            if not attrname.startswith('__'):
                setattr(wrap, attrname, getattr(func, attrname))
        return wrap

    if function:
        return event_view_wrapper(function, require_live=require_live)
    return event_view_wrapper


def event_view(function=None, require_live=True):
    warnings.warn('The event_view decorator is deprecated since it will be automatically applied by the URL routing '
                  'layer when you use event_urls.',
                  DeprecationWarning)

    def noop(fn):
        return fn

    return function or noop
