from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.urlresolvers import get_script_prefix, resolve
from django.http import Http404
from django.shortcuts import redirect, resolve_url
from django.utils.deprecation import MiddlewareMixin
from django.utils.encoding import force_str
from django.utils.translation import ugettext as _

from pretix.base.models import (
    Event, EventPermission, Organizer, OrganizerPermission,
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
    )

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

        events = Event.objects.all() if request.user.is_superuser else request.user.events
        request.user.events_cache = events.order_by(
            "organizer", "date_from").prefetch_related("organizer")
        if 'event' in url.kwargs and 'organizer' in url.kwargs:
            try:
                if request.user.is_superuser:
                    request.event = Event.objects.filter(
                        slug=url.kwargs['event'],
                        organizer__slug=url.kwargs['organizer'],
                    ).select_related('organizer')[0]
                    request.eventperm = EventPermission(
                        event=request.event,
                        user=request.user
                    )
                else:
                    request.event = Event.objects.filter(
                        slug=url.kwargs['event'],
                        permitted__id__exact=request.user.id,
                        organizer__slug=url.kwargs['organizer'],
                    ).select_related('organizer')[0]
                    request.eventperm = EventPermission.objects.get(
                        event=request.event,
                        user=request.user
                    )
                request.organizer = request.event.organizer
            except IndexError:
                raise Http404(_("The selected event was not found or you "
                                "have no permission to administrate it."))
        elif 'organizer' in url.kwargs:
            try:
                if request.user.is_superuser:
                    request.organizer = Organizer.objects.filter(
                        slug=url.kwargs['organizer'],
                    )[0]
                    request.orgaperm = OrganizerPermission(
                        organizer=request.organizer,
                        user=request.user
                    )
                else:
                    request.organizer = Organizer.objects.filter(
                        slug=url.kwargs['organizer'],
                        permitted__id__exact=request.user.id,
                    )[0]
                    request.orgaperm = OrganizerPermission.objects.get(
                        organizer=request.organizer,
                        user=request.user
                    )
            except IndexError:
                raise Http404(_("The selected organizer was not found or you "
                                "have no permission to administrate it."))
