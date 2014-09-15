from django.http import HttpResponseForbidden
from django.utils.translation import ugettext as _

from tixlbase.models import EventPermission


def event_permission_required(function, permission):
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


class EventPermissionRequiredMixin:
    permission = ''

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(EventPermissionRequiredMixin, cls).as_view(**initkwargs)
        return event_permission_required(view, cls.permission)
