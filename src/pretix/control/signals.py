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
of every page in the backend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

nav_event = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal allows you to add additional views to the admin panel
navigation. You will get the request as a keyword argument ``request``.
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

nav_topbar = Signal(
    providing_args=["request"]
)
"""
This signal allows you to add additional views to the top navigation bar.
You will get the request as a keyword argument ``return``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a fontawesome icon name with the key ``icon``, it will be respected depending
on the type of navigation. If set, on desktops only the ``icon`` will be shown.

If you use this, you should read the documentation on :ref:`how to deal with URLs <urlconf>`
in pretix.

This is no ``EventPluginSignal``, so you do not get the event in the ``sender`` argument
and you may get the signal regardless of whether your plugin is active.
"""

event_dashboard_widgets = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to include widgets in the event dashboard. Receivers
should return a list of dictionaries, where each dictionary can have the keys:

* content (str, containing HTML)
* display_size (str, one of "full" (whole row), "big" (half a row) or "small"
  (quarter of a row). May be ignored on small displays, default is "small")
* priority (int, used for ordering, higher comes first, default is 1)
* link (str, optional, if the full widget should be a link)

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

user_dashboard_widgets = Signal(
    providing_args=['user']
)
"""
This signal is sent out to include widgets in the personal user dashboard. Receivers
should return a list of dictionaries, where each dictionary can have the keys:

* content (str, containing HTML)
* display_size (str, one of "full" (whole row), "big" (half a row) or "small"
  (quarter of a row). May be ignored on small displays, default is "small")
* priority (int, used for ordering, higher comes first, default is 1)
* link (str, optional, if the full widget should be a link)

This is a regular django signal (no pretix event signal).
"""

voucher_form_html = EventPluginSignal(
    providing_args=['form']
)
"""
This signal allows you to add additional HTML to the form that is used for modifying vouchers.
You receive the form object in the ``form`` keyword argument.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

voucher_form_class = EventPluginSignal(
    providing_args=['cls']
)
"""
This signal allows you to replace the form class that is used for modifying vouchers.
You will receive the default form class (or the class set by a previous plugin) in the
``cls`` argument so that you can inherit from it.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

quota_detail_html = EventPluginSignal(
    providing_args=['quota']
)
"""
This signal allows you to append HTML to a Quota's detail view. You receive the
quota as argument in the ``quota`` keyword argument.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

organizer_edit_tabs = Signal(
    providing_args=['organizer', 'request']
)
"""
This signal is sent out to include tabs on the detail page of an organizer. Receivers
should return a tuple with the first item being the tab title and the second item
being the content as HTML. The receivers get the ``organizer`` and the ``request`` as
keyword arguments.

This is a regular django signal (no pretix event signal).
"""
