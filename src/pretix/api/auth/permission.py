from rest_framework.permissions import SAFE_METHODS, BasePermission

from pretix.base.models.organizer import TeamAPIToken


class EventPermission(BasePermission):
    model = TeamAPIToken

    def has_permission(self, request, view):
        if not request.user.is_authenticated and not isinstance(request.auth, TeamAPIToken):
            if request.method in SAFE_METHODS and request.path.startswith('/api/v1/docs/'):
                return True
            return False

        """
        if 'event' in request.kwargs:
            pass  # …

        if 'organizer' in request.kwargs:
            pass  # …
        """
        return True
