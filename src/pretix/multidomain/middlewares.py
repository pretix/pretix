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

import time
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.sessions.middleware import (
    SessionMiddleware as BaseSessionMiddleware,
)
from django.core.cache import cache
from django.core.exceptions import DisallowedHost
from django.http.request import split_domain_port
from django.middleware.csrf import (
    CSRF_SESSION_KEY, CsrfViewMiddleware as BaseCsrfMiddleware,
)
from django.shortcuts import render
from django.urls import set_urlconf
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import http_date
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer
from pretix.helpers.cookies import set_cookie_without_samesite
from pretix.multidomain.models import KnownDomain

LOCAL_HOST_NAMES = ('testserver', 'localhost')


class MultiDomainMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # We try three options, in order of decreasing preference.
        if settings.USE_X_FORWARDED_HOST and ('X-Forwarded-Host' in request.headers):
            host = request.headers['X-Forwarded-Host']
        elif 'Host' in request.headers:
            host = request.headers['Host']
        else:
            # Reconstruct the host using the algorithm from PEP 333.
            host = request.META['SERVER_NAME']
            server_port = str(request.META['SERVER_PORT'])
            if server_port != ('443' if request.is_secure() else '80'):
                host = '%s:%s' % (host, server_port)

        domain, port = split_domain_port(host)
        default_domain, default_port = split_domain_port(urlparse(settings.SITE_URL).netloc)
        request.port = int(port) if port else None
        request.host = domain
        if domain == default_domain:
            request.urlconf = "pretix.multidomain.maindomain_urlconf"
        elif domain:
            cached = cache.get('pretix_multidomain_instance_{}'.format(domain))

            if cached is None:
                try:
                    kd = KnownDomain.objects.select_related('organizer', 'event').get(domainname=domain)  # noqa
                    orga = kd.organizer
                    event = kd.event
                except KnownDomain.DoesNotExist:
                    orga = False
                    event = False
                cache.set(
                    'pretix_multidomain_instance_{}'.format(domain),
                    (orga.pk if orga else None, event.pk if event else None),
                    3600
                )
            else:
                orga, event = cached

            if event:
                request.event_domain = True
                if isinstance(event, Event):
                    request.organizer = orga
                    request.event = event
                else:
                    with scopes_disabled():
                        request.event = Event.objects.select_related('organizer').get(pk=event)
                        request.organizer = request.event.organizer
                request.urlconf = "pretix.multidomain.event_domain_urlconf"
            elif orga:
                request.organizer_domain = True
                request.organizer = orga if isinstance(orga, Organizer) else Organizer.objects.get(pk=orga)
                request.urlconf = "pretix.multidomain.organizer_domain_urlconf"
            elif settings.DEBUG or domain in LOCAL_HOST_NAMES:
                request.urlconf = "pretix.multidomain.maindomain_urlconf"
            else:
                with scopes_disabled():
                    is_fresh_install = not Event.objects.exists()
                return render(request, '400_hostname.html', {
                    'header_host': domain,
                    'site_host': default_domain,
                    'settings': settings,
                    'xfh': request.headers.get('X-Forwarded-Host'),
                    'is_fresh_install': is_fresh_install,
                }, status=400)
        else:
            raise DisallowedHost("Invalid HTTP_HOST header: %r." % host)

        # We need to manually set the urlconf for the whole thread. Normally, Django's basic request handling
        # would do this for us, but we already need it in place for the other middlewares.
        set_urlconf(request.urlconf)

    def process_response(self, request, response):
        if getattr(request, "urlconf", None):
            patch_vary_headers(response, ('Host',))
        return response


class SessionMiddleware(BaseSessionMiddleware):
    """
    We override the default implementation from django because we need to handle
    cookie domains differently depending on whether we are on the main domain or
    a custom domain.
    """

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            pass
        else:
            # First check if we need to delete this cookie.
            # The session should be deleted only if the session is entirely empty
            if settings.SESSION_COOKIE_NAME in request.COOKIES and empty:
                response.delete_cookie(settings.SESSION_COOKIE_NAME)
            else:
                if accessed:
                    patch_vary_headers(response, ('Cookie',))
                if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                    if request.session.get_expire_at_browser_close():
                        max_age = None
                        expires = None
                    else:
                        max_age = request.session.get_expiry_age()
                        expires_time = time.time() + max_age
                        expires = http_date(expires_time)
                    # Save the session data and refresh the client cookie.
                    # Skip session save for 500 responses, refs #3881.
                    if response.status_code != 500:
                        request.session.save()
                        set_cookie_without_samesite(
                            request, response,
                            settings.SESSION_COOKIE_NAME,
                            request.session.session_key, max_age=max_age,
                            expires=expires,
                            domain=get_cookie_domain(request),
                            path=settings.SESSION_COOKIE_PATH,
                            secure=request.scheme == 'https',
                            httponly=settings.SESSION_COOKIE_HTTPONLY or None
                        )
        return response


class CsrfViewMiddleware(BaseCsrfMiddleware):
    """
    We override the default implementation from django because we need to handle
    cookie domains differently depending on whether we are on the main domain or
    a custom domain.
    """

    def _set_csrf_cookie(self, request, response):
        if settings.CSRF_USE_SESSIONS:
            if request.session.get(CSRF_SESSION_KEY) != request.META["CSRF_COOKIE"]:
                request.session[CSRF_SESSION_KEY] = request.META["CSRF_COOKIE"]
        else:
            # Set the CSRF cookie even if it's already set, so we renew
            # the expiry timer.
            set_cookie_without_samesite(
                request, response,
                settings.CSRF_COOKIE_NAME,
                request.META["CSRF_COOKIE"],
                max_age=settings.CSRF_COOKIE_AGE,
                domain=get_cookie_domain(request),
                path=settings.CSRF_COOKIE_PATH,
                secure=request.scheme == 'https',
                httponly=settings.CSRF_COOKIE_HTTPONLY
            )
            # Content varies with the CSRF cookie, so set the Vary header.
            patch_vary_headers(response, ('Cookie',))


def get_cookie_domain(request):
    if '.' not in request.host:
        # As per spec, browsers do not accept cookie domains without dots in it,
        # e.g. "localhost", see http://curl.haxx.se/rfc/cookie_spec.html
        return None
    default_domain, default_port = split_domain_port(urlparse(settings.SITE_URL).netloc)
    if request.host == default_domain:
        # We are on our main domain, set the cookie domain the user has chosen
        return settings.SESSION_COOKIE_DOMAIN
    else:
        # We are on an organizer's custom domain, set no cookie domain, as we do not want
        # the cookies to be present on any other domain. Setting an explicit value can be
        # dangerous, see http://erik.io/blog/2014/03/04/definitive-guide-to-cookie-domains/
        return None
