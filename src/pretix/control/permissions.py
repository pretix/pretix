from urllib.parse import quote

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _


def event_permission_required(permission):
    """
    This view decorator rejects all requests with a 403 response which are not from
    users having the given permission for the event the request is associated with.
    """
    if permission == 'can_change_settings':
        # Legacy support
        permission = 'can_change_event_settings'

    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()

            allowed = (
                request.user.has_event_permission(request.organizer, request.event, permission, request=request)
            )
            if allowed:
                return function(request, *args, **kw)

            raise PermissionDenied(_('You do not have permission to view this content.'))
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


def organizer_permission_required(permission):
    """
    This view decorator rejects all requests with a 403 response which are not from
    users having the given permission for the event the request is associated with.
    """
    if permission == 'can_change_settings':
        # Legacy support
        permission = 'can_change_organizer_settings'

    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()

            allowed = request.user.has_organizer_permission(request.organizer, permission, request=request)
            if allowed:
                return function(request, *args, **kw)

            raise PermissionDenied(_('You do not have permission to view this content.'))
        return wrapper
    return decorator


class OrganizerPermissionRequiredMixin:
    """
    This mixin is equivalent to the organizer_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    permission = ''

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(OrganizerPermissionRequiredMixin, cls).as_view(**initkwargs)
        return organizer_permission_required(cls.permission)(view)


def administrator_permission_required():
    """
    This view decorator rejects all requests with a 403 response which are not from
    users with a current staff member session.
    """
    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()
            if not request.user.has_active_staff_session(request.session.session_key):
                if request.user.is_staff:
                    return redirect(reverse('control:user.sudo') + '?next=' + quote(request.path))
                raise PermissionDenied(_('You do not have permission to view this content.'))
            return function(request, *args, **kw)
        return wrapper
    return decorator


def staff_member_required():
    """
    This view decorator rejects all requests with a 403 response which are not staff
    members (but do not need to have an active session).
    """
    def decorator(function):
        def wrapper(request, *args, **kw):
            if not request.user.is_authenticated:  # NOQA
                # just a double check, should not ever happen
                raise PermissionDenied()
            if not request.user.is_staff:
                raise PermissionDenied(_('You do not have permission to view this content.'))
            return function(request, *args, **kw)
        return wrapper
    return decorator


class AdministratorPermissionRequiredMixin:
    """
    This mixin is equivalent to the administrator_permission_required view decorator but
    is in a form suitable for class-based views.
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(AdministratorPermissionRequiredMixin, cls).as_view(**initkwargs)
        return administrator_permission_required()(view)


class StaffMemberRequiredMixin:
    """
    This mixin is equivalent to the staff_memer_required view decorator but
    is in a form suitable for class-based views.
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(StaffMemberRequiredMixin, cls).as_view(**initkwargs)
        return staff_member_required()(view)
