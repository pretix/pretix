.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

HTML head injection
-------------------

These two signals allow you to put code inside the HTML ``<head>`` tag
of every page. One signal is for the frontend, one for the backend. You
will get the request as a keyword argument ``request`` and can return plain
HTML. The ``request`` object will have an attribute ``event``.

* ``pretix.presale.signals.html_head``
* ``pretix.control.signals.html_head``

Admin navigation
----------------
The following signals allow you to add additional views to the admin panel
navigation. You will get the request as a keyword argument ``return``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a fontawesome icon name with the key ``icon``, it will  be respected depending
on the type of navigation. You should also return an ``active`` key with a boolean
set to ``True``, when this item should be marked as active. The ``request`` object
will have an attribute ``event``.

``pretix.control.signals.nav_event``:
    The sidebar navigation when the admin has selected an event.
