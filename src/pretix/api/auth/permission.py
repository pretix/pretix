from rest_framework.permissions import SAFE_METHODS, BasePermission

from pretix.api.models import OAuthAccessToken
from pretix.base.models import Device, Event, User
from pretix.base.models.auth import SuperuserPermissionSet
from pretix.base.models.organizer import TeamAPIToken
from pretix.helpers.security import (
    SessionInvalid, SessionReauthRequired, assert_session_valid,
)


class EventPermission(BasePermission):

    def has_permission(self, request, view):
        if not request.user.is_authenticated and not isinstance(request.auth, (Device, TeamAPIToken)):
            return False

        if request.method not in SAFE_METHODS and hasattr(view, 'write_permission'):
            required_permission = getattr(view, 'write_permission')
        elif hasattr(view, 'permission'):
            required_permission = getattr(view, 'permission')
        else:
            required_permission = None

        if request.user.is_authenticated:
            try:
                # If this logic is updated, make sure to also update the logic in pretix/control/middleware.py
                assert_session_valid(request)
            except SessionInvalid:
                return False
            except SessionReauthRequired:
                return False

        perm_holder = (request.auth if isinstance(request.auth, (Device, TeamAPIToken))
                       else request.user)
        if 'event' in request.resolver_match.kwargs and 'organizer' in request.resolver_match.kwargs:
            request.event = Event.objects.filter(
                slug=request.resolver_match.kwargs['event'],
                organizer__slug=request.resolver_match.kwargs['organizer'],
            ).select_related('organizer').first()
            if not request.event or not perm_holder.has_event_permission(request.event.organizer, request.event, request=request):
                return False
            request.organizer = request.event.organizer
            if isinstance(perm_holder, User) and perm_holder.has_active_staff_session(request.session.session_key):
                request.eventpermset = SuperuserPermissionSet()
            else:
                request.eventpermset = perm_holder.get_event_permission_set(request.organizer, request.event)

            if required_permission and required_permission not in request.eventpermset:
                return False

        elif 'organizer' in request.resolver_match.kwargs:
            if not request.organizer or not perm_holder.has_organizer_permission(request.organizer, request=request):
                return False
            if isinstance(perm_holder, User) and perm_holder.has_active_staff_session(request.session.session_key):
                request.orgapermset = SuperuserPermissionSet()
            else:
                request.orgapermset = perm_holder.get_organizer_permission_set(request.organizer)

            if required_permission and required_permission not in request.orgapermset:
                return False

        if isinstance(request.auth, OAuthAccessToken):
            if not request.auth.allow_scopes(['write']) and request.method not in SAFE_METHODS:
                return False
            if not request.auth.allow_scopes(['read']) and request.method in SAFE_METHODS:
                return False
        if isinstance(request.auth, OAuthAccessToken) and hasattr(request, 'organizer'):
            if not request.auth.organizers.filter(pk=request.organizer.pk).exists():
                return False
        return True


class EventCRUDPermission(EventPermission):
    def has_permission(self, request, view):
        if not super(EventCRUDPermission, self).has_permission(request, view):
            return False
        elif view.action == 'create' and 'can_create_events' not in request.orgapermset:
            return False
        elif view.action == 'destroy' and 'can_change_event_settings' not in request.eventpermset:
            return False
        elif view.action in ['update', 'partial_update'] \
                and 'can_change_event_settings' not in request.eventpermset:
            return False

        return True
