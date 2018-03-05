import hashlib
import time

from django.conf import settings


class SessionInvalid(Exception):
    pass


class SessionReauthRequired(Exception):
    pass


def get_user_agent_hash(request):
    return hashlib.sha256(request.META['HTTP_USER_AGENT'].encode()).hexdigest()


def assert_session_valid(request):
    if not settings.PRETIX_LONG_SESSIONS or not request.session.get('pretix_auth_long_session', False):
        last_used = request.session.get('pretix_auth_last_used', time.time())
        if time.time() - request.session.get('pretix_auth_login_time',
                                             time.time()) > settings.PRETIX_SESSION_TIMEOUT_ABSOLUTE:
            request.session['pretix_auth_login_time'] = 0
            raise SessionInvalid()
        if time.time() - last_used > settings.PRETIX_SESSION_TIMEOUT_RELATIVE:
            raise SessionReauthRequired()

    if 'HTTP_USER_AGENT' in request.META:
        if 'pinned_user_agent' in request.session:
            if request.session.get('pinned_user_agent') != get_user_agent_hash(request):
                raise SessionInvalid()
        else:
            request.session['pinned_user_agent'] = get_user_agent_hash(request)

    request.session['pretix_auth_last_used'] = int(time.time())
    return True
