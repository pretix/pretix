.. _`urlconf`:

Working with URLs
=================

As soon as you write a plugin that provides a new view to the user (or if you want to
contribute to pretix itself), you need to understand how URLs work in pretix as it differs
slightly from the standard Django system.

The reason for the complicated URL handling is that pretix supports custom subdomains for
single organizers. In this example we will use an event organizer with the slug ``bigorg``
that manages an awesome conference with the slug ``awesomecon``. If pretix is installed
on pretix.eu, this event is available by default at ``https://pretix.eu/bigorg/awesomecon/``
and the admin panel is available at ``https://pretix.eu/control/event/bigorg/awesomecon/``.

If the organizer now configures a custom domain like ``tickets.bigorg.com``, his event will
from now on be available on ``https://tickets.bigorg.com/awesomecon/``. The former URL at
``pretix.eu`` will redirect there. It's also possible to do this for just an event, in which
case the event will be available on ``https://tickets.awesomecon.org/``.

However, the admin panel will still only be available on ``pretix.eu`` for convenience and security reasons.

URL routing
-----------

The hard part about implementing this URL routing in Django is that
``https://pretix.eu/bigorg/awesomecon/`` contains two parameters of nearly arbitrary content
and ``https://tickets.bigorg.com/awesomecon/`` contains only one and ``https://tickets.awesomecon.org/`` does not contain any.
The only robust way to do this is by having *separate* URL configuration for those three cases.

In pretix, we therefore do not have a global URL configuration, but three, living in the following modules:

- ``pretix.multidomain.maindomain_urlconf``
- ``pretix.multidomain.organizer_domain_urlconf``
- ``pretix.multidomain.event_domain_urlconf``

We provide some helper utilities to work with these to avoid duplicate configuration of the individual URLs.
The file ``urls.py`` inside your plugin package will be loaded and scanned for URL configuration
automatically and should be provided by any plugin that provides any view.
However, unlike plain Django, we look not only for a ``urlpatterns`` attribute on the module but support other
attributes like ``event_patterns`` and ``organizer_patterns`` as well.

For example, for a simple plugin that adds one URL to the backend and one event-level URL to the frontend, you can
create the following configuration in your ``urls.py``::

    from django.urls import re_path

    from . import views

    urlpatterns = [
        re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/mypluginname/',
                views.AdminView.as_view(), name='backend'),
    ]

    event_patterns = [
        url(r'^mypluginname/', views.FrontendView.as_view(), name='frontend'),
    ]

.. note::
    As you can see, the view in the frontend is not included in the standard Django ``urlpatterns``
    setting but in a separate list with the name ``event_patterns``. This will automatically prepend
    the appropriate parameters to the regex (e.g. the event or the event and the organizer, depending
    on the called domain). For organizer-level views, ``organizer_patterns`` works the same way.

If you only provide URLs in the admin area, you do not need to provide a ``event_patterns`` attribute.

URL reversal
------------

pretix uses Django's URL namespacing feature. The URLs of pretix's core are available in the ``control``
and ``presale`` namespaces, there are only very few URLs in the root namespace. Your plugin's URLs will
be available in the ``plugins:<applabel>`` namespace, e.g. the form of the email sending plugin is
available as ``plugins:sendmail:send``.

Generating a URL for the frontend is a complicated task, because you need to know whether the event's
organizer uses a custom URL or not and then generate the URL with a different domain and different
arguments based on this information. pretix provides some helpers to make this easier. The first helper
is a python method that emulates a behavior similar to ``reverse``:

.. autofunction:: pretix.multidomain.urlreverse.eventreverse

If you need to communicate the URL externally, you can use a different method to ensure that it is always an absolute URL:

.. autofunction:: pretix.multidomain.urlreverse.build_absolute_uri

In addition, there is a template tag that works similar to ``url`` but takes an event or organizer object
as its first argument and can be used like this::

    {% load eventurl %}
    <a href="{% eventurl request.event "presale:event.checkout" step="payment" %}">Pay</a>
    <a href="{% abseventurl request.event "presale:event.checkout" step="payment" %}">Pay</a>

To generate absolute URLs on the main domain, you can use the ``absurl`` template tag::

    {% load eventurl %}
    <a href="{% absmainurl "control:event.settings" organizer=request.event.organizer.slug event=request.event.slug %}">Event settings</a>

Implementation details
----------------------

There are some other caveats when using a design like this, e.g. you have to care about cookie domains
and referrer verification yourself. If you want to see how we built this, look into the ``pretix/multidomain/``
sub-tree.
