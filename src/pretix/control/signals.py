from django.dispatch import Signal

from pretix.base.signals import EventPluginSignal

restriction_formset = EventPluginSignal(
    providing_args=["item"]
)
"""
This signal is sent out to build configuration forms for all restriction formsets
(see plugin API documentation for details).

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

html_head = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal allows you to put code inside the HTML ``<head>`` tag
of every page in the backend. You will get the request as a keyword argument
``request`` and can return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

nav_event = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal allows you to add additional views to the admin panel
navigation. You will get the request as a keyword argument ``return``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a fontawesome icon name with the key ``icon``, it will  be respected depending
on the type of navigation. You should also return an ``active`` key with a boolean
set to ``True``, when this item should be marked as active. The ``request`` object
will have an attribute ``event``.

If you use this, you should read the documentation on :ref:`how to deal with URLs <urlconf>`
in pretix.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

event_dashboard_widgets = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to include widgets to the event dashboard. Receivers
should return a list of dictionaries, where each dictionary can have the keys:

* content (str, containing HTML)
* minimal width (int, widget width in 1/12ths of the page, default ist 3, can be
  ignored on small displays)
* priority (int, used for ordering, higher comes first, default is 1)
* link (str, optional, if the full widget should be a link)

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

user_dashboard_widgets = Signal(
    providing_args=['user']
)
"""
This signal is sent out to include widgets to the personal user dashboard. Receivers
should return a list of dictionaries, where each dictionary can have the keys:

* content (str, containing HTML)
* minimal width (int, widget width in 1/12ths of the page, default ist 3, can be
  ignored on small displays)
* priority (int, used for ordering, higher comes first, default is 1)
* link (str, optional, if the full widget should be a link)

This is a regular django signal (no pretix event signal).
"""
