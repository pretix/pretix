from django.http import HttpResponseForbidden
from django.utils.translation import ugettext as _

from tixlbase.models import EventPermission


def event_permission_required(permission):
    """
    This view decorator rejects all requests with a 403 response which are not from
    users having the given permission for the event the request is associated with.
    """
    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated():
                return HttpResponseForbidden()
            perm = EventPermission.objects.get(
                event=request.event,
                user=request.user
            )
            allowed = False
            try:
                allowed = getattr(perm, permission)
            except AttributeError:
                pass
            if allowed:
                return function(request, *args, **kw)
            return HttpResponseForbidden(_('You do not have permission to view this content.'))
        return wrapper
    return decorator


class EventPermissionRequiredMixin:
    """
    This mixin is equivalent to the event_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    permission = ''

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(EventPermissionRequiredMixin, cls).as_view(**initkwargs)
        return event_permission_required(cls.permission)(view)
