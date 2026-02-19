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
import hashlib
import logging
import time

from django.conf import settings
from django.contrib.gis.geoip2 import GeoIP2
from django.core.cache import cache
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_countries.fields import Country
from geoip2.errors import AddressNotFoundError

from pretix.base.i18n import language
from pretix.base.services.mail import mail
from pretix.helpers.http import get_client_ip
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger(__name__)


class SessionInvalid(Exception):
    pass


class SessionReauthRequired(Exception):
    pass


class Session2FASetupRequired(Exception):
    pass


class SessionPasswordChangeRequired(Exception):
    pass


def get_user_agent_hash(request):
    return hashlib.sha256(request.headers['User-Agent'].encode()).hexdigest()


_geoip = None


def _get_country(request):
    global _geoip

    if not _geoip:
        _geoip = GeoIP2()

    try:
        res = _geoip.country(get_client_ip(request))
    except AddressNotFoundError:
        return None
    return res['country_code']


def assert_session_valid(request):
    if not settings.PRETIX_LONG_SESSIONS or not request.session.get('pretix_auth_long_session', False):
        last_used = request.session.get('pretix_auth_last_used', time.time())
        if time.time() - request.session.get('pretix_auth_login_time',
                                             time.time()) > settings.PRETIX_SESSION_TIMEOUT_ABSOLUTE:
            request.session['pretix_auth_login_time'] = 0
            raise SessionInvalid()
        if time.time() - last_used > settings.PRETIX_SESSION_TIMEOUT_RELATIVE:
            raise SessionReauthRequired()

    if 'User-Agent' in request.headers:
        if 'pinned_user_agent' in request.session:
            if request.session.get('pinned_user_agent') != get_user_agent_hash(request):
                logger.info(f"Backend session for user {request.user.pk} terminated due to user agent change. "
                            f"New agent: \"{request.headers['User-Agent']}\"")
                raise SessionInvalid()
        else:
            request.session['pinned_user_agent'] = get_user_agent_hash(request)

    if settings.HAS_GEOIP:
        client_ip = get_client_ip(request)
        hashed_client_ip = hashlib.sha256(client_ip.encode()).hexdigest()
        country = cache.get_or_set(f'geoip_country_{hashed_client_ip}', lambda: _get_country(request), timeout=300)

        if 'pinned_country' in request.session:
            if request.session.get('pinned_country') != country:
                logger.info(f"Backend session for user {request.user.pk} terminated due to country change. "
                            f"Old country: \"{request.session.get('pinned_country')}\" New country: \"{country}\"")
                raise SessionInvalid()
        else:
            request.session['pinned_country'] = country

    request.session['pretix_auth_last_used'] = int(time.time())

    if request.user.needs_password_change:
        raise SessionPasswordChangeRequired()

    force_2fa = not request.user.require_2fa and (
        settings.PRETIX_OBLIGATORY_2FA is True or
        (settings.PRETIX_OBLIGATORY_2FA == "staff" and request.user.is_staff) or
        cache.get_or_set(
            f'user_2fa_team_{request.user.pk}',
            lambda: request.user.teams.filter(require_2fa=True).exists(),
            timeout=300
        )
    )
    if force_2fa:
        raise Session2FASetupRequired()

    return True


def handle_login_source(user, request):
    from ua_parser import user_agent_parser

    parsed_string = user_agent_parser.Parse(request.headers.get("User-Agent", ""))
    country = None

    if settings.HAS_GEOIP:
        client_ip = get_client_ip(request)
        hashed_client_ip = hashlib.sha256(client_ip.encode()).hexdigest()
        country = cache.get_or_set(f'geoip_country_{hashed_client_ip}', lambda: _get_country(request), timeout=300)
        if country == "None":
            country = None

    src, created = user.known_login_sources.update_or_create(
        agent_type=parsed_string.get("user_agent").get("family"),
        os_type=parsed_string.get("os").get("family"),
        device_type=parsed_string.get("device").get("family"),
        country=country,
        defaults={
            "last_seen": now(),
        }
    )

    if created:
        user.log_action('pretix.control.auth.user.new_source', user=user, data={
            "agent_type": src.agent_type,
            "os_type": src.os_type,
            "device_type": src.device_type,
            "country": str(src.country) if src.country else "?",
        })
        if user.known_login_sources.count() > 1:
            # Do not send on first login or first login after introduction of this feature:
            with language(user.locale):
                mail(
                    user.email,
                    _('Login from new source detected'),
                    'pretixcontrol/email/login_notice.txt',
                    {
                        'source': src,
                        'country': Country(str(country)).name if country else _('Unknown country'),
                        'instance': settings.PRETIX_INSTANCE_NAME,
                        'url': build_absolute_uri('control:user.settings')
                    },
                    event=None,
                    user=user,
                    locale=user.locale
                )
