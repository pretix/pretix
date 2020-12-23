Permissions
===========

pretix uses a fine-grained permission system to control who is allowed to control what parts of the system.
The central concept here is the concept of *Teams*. You can read more on `configuring teams and permissions <user-teams>`_
and the :class:`pretix.base.models.Team` model in the respective parts of the documentation. The basic digest is:
An organizer account can have any number of teams, and any number of users can be part of a team. A team can be
assigned a set of permissions and connected to some or all of the events of the organizer.

A second way to access pretix is via the REST API, which allows authentication via tokens that are bound to a team,
but not to a user. You can read more at :class:`pretix.base.models.TeamAPIToken`. This page will show you how to
work with permissions in plugins and within the pretix code base.

Requiring permissions for a view
--------------------------------

pretix provides a number of useful mixins and decorators that allow you to specify that a user needs a certain
permission level to access a view:

.. code-block:: python

    from pretix.control.permissions import (
        OrganizerPermissionRequiredMixin, organizer_permission_required
    )


    class MyOrgaView(OrganizerPermissionRequiredMixin, View):
        permission = 'can_change_organizer_settings'
        # Only users with the permission ``can_change_organizer_settings`` on
        # this organizer can access this


    class MyOtherOrgaView(OrganizerPermissionRequiredMixin, View):
        permission = None
        # Only users with *any* permission on this organizer can access this


    @organizer_permission_required('can_change_organizer_settings')
    def my_orga_view(request, organizer, **kwargs):
        # Only users with the permission ``can_change_organizer_settings`` on
        # this organizer can access this


    @organizer_permission_required()
    def my_other_orga_view(request, organizer, **kwargs):
        # Only users with *any* permission on this organizer can access this


Of course, the same is available on event level:

.. code-block:: python

    from pretix.control.permissions import (
        EventPermissionRequiredMixin, event_permission_required
    )


    class MyEventView(EventPermissionRequiredMixin, View):
        permission = 'can_change_event_settings'
        # Only users with the permission ``can_change_event_settings`` on
        # this event can access this


    class MyOtherEventView(EventPermissionRequiredMixin, View):
        permission = None
        # Only users with *any* permission on this event can access this


    @event_permission_required('can_change_event_settings')
    def my_event_view(request, organizer, **kwargs):
        # Only users with the permission ``can_change_event_settings`` on
        # this event can access this


    @event_permission_required()
    def my_other_event_view(request, organizer, **kwargs):
        # Only users with *any* permission on this event can access this

You can also require that this view is only accessible by system administrators with an active "admin session"
(see below for what this means):

.. code-block:: python

    from pretix.control.permissions import (
        AdministratorPermissionRequiredMixin, administrator_permission_required
    )


    class MyGlobalView(AdministratorPermissionRequiredMixin, View):
        # ...


    @administrator_permission_required
    def my_global_view(request, organizer, **kwargs):
        # ...

In rare cases it might also be useful to expose a feature only to people who have a staff account but do not
necessarily have an active admin session:

.. code-block:: python

    from pretix.control.permissions import (
        StaffMemberRequiredMixin, staff_member_required
    )


    class MyGlobalView(StaffMemberRequiredMixin, View):
        # ...


    @staff_member_required
    def my_global_view(request, organizer, **kwargs):
        # ...



Requiring permissions in the REST API
-------------------------------------

When creating your own ``viewset`` using Django REST framework, you just need to set the ``permission`` attribute
and pretix will check it automatically for you::

    class MyModelViewSet(viewsets.ReadOnlyModelViewSet):
        permission = 'can_view_orders'

Checking permission in code
---------------------------

If you need to work with permissions manually, there are a couple of useful helper methods on the :class:`pretix.base.models.Event`,
:class:`pretix.base.models.User` and :class:`pretix.base.models.TeamAPIToken` classes. Here's a quick overview.

Return all users that are in any team that is connected to this event::

    >>> event.get_users_with_any_permission()
    <QuerySet: …>

Return all users that are in a team with a specific permission for this event::

    >>> event.get_users_with_permission('can_change_event_settings')
    <QuerySet: …>

Determine if a user has a certain permission for a specific event::

    >>> user.has_event_permission(organizer, event, 'can_change_event_settings', request=request)
    True

Determine if a user has any permission for a specific event::

    >>> user.has_event_permission(organizer, event, request=request)
    True

In the two previous commands, the ``request`` argument is optional, but required to support staff sessions (see below).

The same method exists for organizer-level permissions::

    >>> user.has_organizer_permission(organizer, 'can_change_event_settings', request=request)
    True

Sometimes, it might be more useful to get the set of permissions at once::

    >>> user.get_event_permission_set(organizer, event)
    {'can_change_event_settings', 'can_view_orders', 'can_change_orders'}

    >>> user.get_organizer_permission_set(organizer, event)
    {'can_change_organizer_settings', 'can_create_events'}

Within a view on the ``/control`` subpath, the results of these two methods are already available in the
``request.eventpermset`` and ``request.orgapermset`` properties. This makes it convenient to query them in templates::

    {% if "can_change_orders" in request.eventpermset %}
        …
    {% endif %}

You can also do the reverse to get any events a user has access to::

    >>> user.get_events_with_permission('can_change_event_settings', request=request)
    <QuerySet: …>

    >>> user.get_events_with_any_permission(request=request)
    <QuerySet: …>

Most of these methods work identically on :class:`pretix.base.models.TeamAPIToken`.

Staff sessions
--------------

.. versionchanged:: 1.14

   In 1.14, the ``User.is_superuser`` attribute has been deprecated and statically set to return ``False``. Staff
   sessions have been newly introduced.

System administrators of a pretix instance are identified by the ``is_staff`` attribute on the user model. By default,
the regular permission rules apply for users with ``is_staff = True``. The only difference is that such users can
temporarily turn on "staff mode" via a button in the user interface that grants them **all permissions** as long as
staff mode is active. You can check if a user is in staff mode using their session key:

    >>> user.has_active_staff_session(request.session.session_key)
    False

Staff mode has a hard time limit and during staff mode, a middleware will log all requests made by that user. Later,
the user is able to also save a message to comment on what they did in their administrative session. This feature is
intended to help compliance with data protection rules as imposed e.g. by GDPR.
