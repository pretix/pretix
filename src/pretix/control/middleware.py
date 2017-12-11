from urllib.parse import quote, urljoin, urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME, logout
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, resolve_url
from django.urls import get_script_prefix, resolve, reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.encoding import force_str
from django.utils.translation import ugettext as _
from hijack.templatetags.hijack_tags import is_hijacked

from pretix.base.models import Event, Organizer
from pretix.base.models.auth import SuperuserPermissionSet, User
from pretix.helpers.security import (
    SessionInvalid, SessionReauthRequired, assert_session_valid,
)


class PermissionMiddleware(MiddlewareMixin):
    """
    This middleware enforces all requests to the control app to require login.
    Additionally, it enforces all requests to "control:event." URLs
    to be for an event the user has basic access to.
    """

    EXCEPTIONS = (
        "auth.login",
        "auth.login.2fa",
        "auth.register",
        "auth.forgot",
        "auth.forgot.recover",
        "auth.invite",
        "user.settings.notifications.off",
    )

    def _login_redirect(self, request):
        # Taken from django/contrib/auth/decorators.py
        path = request.build_absolute_uri()
        # urlparse chokes on lazy objects in Python 3, force to str
        resolved_login_url = force_str(
            resolve_url(settings.LOGIN_URL_CONTROL))
        # If the login url is the same scheme and net location then just
        # use the path as the "next" url.
        login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
        current_scheme, current_netloc = urlparse(path)[:2]
        if ((not login_scheme or login_scheme == current_scheme) and
                (not login_netloc or login_netloc == current_netloc)):
            path = request.get_full_path()
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(
            path, resolved_login_url, REDIRECT_FIELD_NAME)

    def process_request(self, request):
        url = resolve(request.path_info)
        url_name = url.url_name

        if not request.path.startswith(get_script_prefix() + 'control'):
            # This middleware should only touch the /control subpath
            return

        if hasattr(request, 'organizer'):
            # If the user is on a organizer's subdomain, he should be redirected to pretix
            return redirect(urljoin(settings.SITE_URL, request.get_full_path()))
        if url_name in self.EXCEPTIONS:
            return
        if not request.user.is_authenticated:
            return self._login_redirect(request)

        try:
            # If this logic is updated, make sure to also update the logic in pretix/api/auth/permission.py
            assert_session_valid(request)
        except SessionInvalid:
            logout(request)
            return self._login_redirect(request)
        except SessionReauthRequired:
            if url_name not in ('user.reauth', 'auth.logout'):
                return redirect(reverse('control:user.reauth') + '?next=' + quote(request.get_full_path()))

        if 'event' in url.kwargs and 'organizer' in url.kwargs:
            request.event = Event.objects.filter(
                slug=url.kwargs['event'],
                organizer__slug=url.kwargs['organizer'],
            ).select_related('organizer').first()
            if not request.event or not request.user.has_event_permission(request.event.organizer, request.event,
                                                                          request=request):
                raise Http404(_("The selected event was not found or you "
                                "have no permission to administrate it."))
            request.organizer = request.event.organizer
            if request.user.has_active_staff_session(request.session.session_key):
                request.eventpermset = SuperuserPermissionSet()
            else:
                request.eventpermset = request.user.get_event_permission_set(request.organizer, request.event)
        elif 'organizer' in url.kwargs:
            request.organizer = Organizer.objects.filter(
                slug=url.kwargs['organizer'],
            ).first()
            if not request.organizer or not request.user.has_organizer_permission(request.organizer, request=request):
                raise Http404(_("The selected organizer was not found or you "
                                "have no permission to administrate it."))
            if request.user.has_active_staff_session(request.session.session_key):
                request.orgapermset = SuperuserPermissionSet()
            else:
                request.orgapermset = request.user.get_organizer_permission_set(request.organizer)


class AuditLogMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(get_script_prefix() + 'control') and request.user.is_authenticated:
            if is_hijacked(request):
                hijack_history = request.session.get('hijack_history', False)
                hijacker = get_object_or_404(User, pk=hijack_history[0])
                ss = hijacker.get_active_staff_session(request.session.get('hijacker_session'))
                if ss:
                    ss.logs.create(
                        url=request.path,
                        method=request.method,
                        impersonating=request.user
                    )
            else:
                ss = request.user.get_active_staff_session(request.session.session_key)
                if ss:
                    ss.logs.create(
                        url=request.path,
                        method=request.method
                    )

        response = self.get_response(request)
        return response
