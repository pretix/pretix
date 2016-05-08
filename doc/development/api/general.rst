.. highlight:: python
   :linenothreshold: 5

General APIs
============

This page lists some general signals and hooks which do not belong to a
specific type of plugin but might come in handy for various plugins.

HTML head injection
-------------------

These two signals allow you to put code inside the HTML ``<head>`` tag
of every page. One signal is for the front end, one for the back end. You
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

Order events
------------

There are multiple signals that will be sent out in the ordering cycle:

``pretix.base.signals.order_placed``:
    Sent out every time an order has been created. Provides the ``order`` as the only
    keyword argument.

``pretix.base.signals.order_paid``:
    Sent out every time an order has been paid. Provides the ``order`` as the only
    keyword argument.


Displaying of log entries
-------------------------

To display an instance of the ``LogEntry`` model to a human user,
``pretix.base.signals.logentry_display`` will be sent out with a ``logentry`` argument.

The first received response that is not ``None`` will be used to display the log entry
to the user.


Periodic tasks
--------------

The ``pretix.base.signals.periodic_task`` is a regular django signal (no pretix event
signal) that we send out every time the periodic task cronjob runs. This interval
is not sharply defined, it can be everything between a minute and a day. The actions
you perform should be idempotent, i.e. it should not make a difference if this is send
out more often than expected.
