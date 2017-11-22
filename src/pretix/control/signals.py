from django.dispatch import Signal

from pretix.base.signals import DeprecatedSignal, EventPluginSignal

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
You will get the request as a keyword argument ``request``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a fontawesome icon name with the key ``icon``, it will be respected depending
on the type of navigation. If set, on desktops only the ``icon`` will be shown.
The ``title`` property can be used to set the alternative text.

If you use this, you should read the documentation on :ref:`how to deal with URLs <urlconf>`
in pretix.

This is no ``EventPluginSignal``, so you do not get the event in the ``sender`` argument
and you may get the signal regardless of whether your plugin is active.
"""

nav_global = Signal(
    providing_args=["request"]
)
"""
This signal allows you to add additional views to the navigation bar when no event is
selected. You will get the request as a keyword argument ``request``.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You can also return
a fontawesome icon name with the key ``icon``, it will  be respected depending
on the type of navigation. You should also return an ``active`` key with a boolean
set to ``True``, when this item should be marked as active.

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
An additional keyword argument ``subevent`` *can* contain a sub-event.
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

voucher_form_validation = EventPluginSignal(
    providing_args=['form']
)
"""
This signal allows you to add additional validation to the form that is used for
creating and modifying vouchers. You will receive the form instance in the ``form``
argument and the current data state in the ``data`` argument.

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

organizer_edit_tabs = DeprecatedSignal(
    providing_args=['organizer', 'request']
)
"""
Deprecated signal, no longer works. We just keep the definition so old plugins don't
break the installation.
"""


nav_organizer = Signal(
    providing_args=['organizer', 'request']
)
"""
This signal is sent out to include tab links on the detail page of an organizer.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You should also return
an ``active`` key with a boolean set to ``True``, when this item should be marked
as active.

If your linked view should stay in the tab-like context of this page, we recommend
that you use ``pretix.control.views.organizer.OrganizerDetailViewMixin`` for your view
and your template inherits from ``pretixcontrol/organizers/base.html``.

This is a regular django signal (no pretix event signal). Receivers will be passed
the keyword arguments ``organizer`` and ``request``.
"""

order_info = EventPluginSignal(
    providing_args=["order", "request"]
)
"""
This signal is sent out to display additional information on the order detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
Additionally, the argument ``order`` and ``request`` are available.
"""


nav_event_settings = EventPluginSignal(
    providing_args=['request']
)
"""
This signal is sent out to include tab links on the settings page of an event.
Receivers are expected to return a list of dictionaries. The dictionaries
should contain at least the keys ``label`` and ``url``. You should also return
an ``active`` key with a boolean set to ``True``, when this item should be marked
as active.

If your linked view should stay in the tab-like context of this page, we recommend
that you use ``pretix.control.views.event.EventSettingsViewMixin`` for your view
and your template inherits from ``pretixcontrol/event/settings_base.html``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
A second keyword argument ``request`` will contain the request object.
"""

event_settings_widget = EventPluginSignal(
    providing_args=['request']
)
"""
This signal is sent out to include template snippets on the settings page of an event
that allows generating a pretix Widget code.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
A second keyword argument ``request`` will contain the request object.
"""
