.. highlight:: python
   :linenothreshold: 5

.. _`customview`:

Creating custom views
=====================

This page describes how to provide a custom view from within your plugin. Before you start
reading this page, please read and understand how :ref:`URL handling <urlconf>` works in
pretix.

Control panel views
-------------------

If you want to add a custom view to the control area of an event, just register an URL in your
``urls.py`` that lives in the ``/control/`` subpath::

    from django.conf.urls import url

    from . import views

    urlpatterns = [
        url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/mypluginname/',
            views.admin_view, name='backend'),
    ]

It is required that your URL paramaters are called ``organizer`` and ``event``. If you want to
install a view on organizer level, you can leave out the ``event``.

You can then implement the view as you would normally do. Our middleware will automatically
detect the ``/control/`` subpath and will ensure the following things if this is an URL with
both the ``event`` and ``organizer`` parameters:

* The user is logged in
* The ``request.event`` attribute contains the current event
* The ``request.organizer`` attribute contains the event's organizer
* The user has permission to access view the current event

If only the ``organizer`` parameter is present, it will be ensured that:

* The user is logged in
* The ``request.organizer`` attribute contains the event's organizer
* The user has permission to access view the current organizer

If you want to require specific permission types, we provide you with a decorator or a mixin for
your views::

    from pretix.control.permissions import (
        event_permission_required, EventPermissionRequiredMixin
    )

    class AdminView(EventPermissionRequiredMixin, View):
        permission = 'can_view_orders'

        ...


    @event_permission_required('can_view_orders')
    def admin_view(request, organizer, event):
        ...

Similarly, there is ``organizer_permission_required`` and ``OrganizerPermissionRequiredMixin``.

Frontend views
--------------

Including a custom view into the participant-facing frontend is a little bit different as there is
no path prefix like ``control/``.

First, define your URL in your ``urls.py``, but this time in the ``event_patterns`` section::

    from django.conf.urls import url

    from . import views

    event_patterns = [
        url(r'^mypluginname/', views.frontend_view, name='frontend'),
    ]

You can then implement a view as you would normally do, but you need to apply a decorator to your
view if you want pretix's default behavior::

    from pretix.presale.utils import event_view

    @event_view
    def some_event_view(request, *args, **kwargs):
        ...

This decorator will check the URL arguments for their ``event`` and ``organizer`` parameters and
correctly ensure that:

* The requested event exists
* The requested event is activated (can be overridden by decorating with ``@event_view(require_live=False)``)
* The event is accessed via the domain it should be accessed
* The ``request.event`` attribute contains the correct ``Event`` object
* The ``request.organizer`` attribute contains the correct ``Organizer`` object
* The locale is set correctly
