from rest_framework.permissions import SAFE_METHODS, BasePermission

from pretix.base.models import Event
from pretix.base.models.organizer import Organizer, TeamAPIToken


class EventPermission(BasePermission):
    model = TeamAPIToken

    def has_permission(self, request, view):
        if not request.user.is_authenticated and not isinstance(request.auth, TeamAPIToken):
            if request.method in SAFE_METHODS and request.path.startswith('/api/v1/docs/'):
                return True
            return False

        perm_holder = (request.auth if isinstance(request.auth, TeamAPIToken)
                       else request.user)
        if 'event' in request.resolver_match.kwargs and 'organizer' in request.resolver_match.kwargs:
            request.event = Event.objects.filter(
                slug=request.resolver_match.kwargs['event'],
                organizer__slug=request.resolver_match.kwargs['organizer'],
            ).select_related('organizer').first()
            if not request.event or not perm_holder.has_event_permission(request.event.organizer, request.event):
                return False
            request.organizer = request.event.organizer
            request.eventpermset = perm_holder.get_event_permission_set(request.organizer, request.event)

            if hasattr(view, 'permission'):
                if view.permission and view.permission not in request.eventpermset:
                    return False

        elif 'organizer' in request.resolver_match.kwargs:
            request.organizer = Organizer.objects.filter(
                slug=request.resolver_match.kwargs['organizer'],
            ).first()
            if not request.organizer or not perm_holder.has_organizer_permission(request.organizer):
                return False
            request.orgapermset = perm_holder.get_organizer_permission_set(request.organizer)

            if hasattr(view, 'permission'):
                if view.permission and view.permission not in request.orgapermset:
                    return False
        return True
