from django.dispatch import Signal

from pretix.base.signals import DeprecatedSignal, EventPluginSignal

html_page_start = Signal(
    providing_args=[]
)
"""
This signal allows you to put code in the beginning of the main page for every
page in the backend. You are expected to return HTML.

The ``sender`` keyword argument will contain the request.
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

You can optionally create sub-items to create hierarchical navigation. There are two
ways to achieve this: Either you specify a key ``children`` on your top navigation item
that contains a list of navigation items (as dictionaries), or you specify a ``parent``
key with the ``url`` value of the designated parent item.
The latter method also allows you to register navigation items as a sub-item of existing ones.

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

You can optionally create sub-items to create hierarchical navigation. There are two
ways to achieve this: Either you specify a key ``children`` on your top navigation item
that contains a list of navigation items (as dictionaries), or you specify a ``parent``
key with the ``url`` value of the designated parent item.
The latter method also allows you to register navigation items as a sub-item of existing ones.

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
* url (str, optional, if the full widget should be a link)

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
* url (str, optional, if the full widget should be a link)

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

You can optionally create sub-items to create hierarchical navigation. There are two
ways to achieve this: Either you specify a key ``children`` on your top navigation item
that contains a list of navigation items (as dictionaries), or you specify a ``parent``
key with the ``url`` value of the designated parent item.
The latter method also allows you to register navigation items as a sub-item of existing ones.

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

order_position_buttons = EventPluginSignal(
    providing_args=["order", "position", "request"]
)
"""
This signal is sent out to display additional buttons for a single position of an order.

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

item_forms = EventPluginSignal(
    providing_args=['request', 'item']
)
"""
This signal allows you to return additional forms that should be rendered on the product
modification page. You are passed ``request`` and ``item`` arguments and are expected to return
an instance of a form class that you bind yourself when appropriate. Your form will be executed
as part of the standard validation and rendering cycle and rendered using default bootstrap
styles. It is advisable to set a prefix for your form to avoid clashes with other plugins.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

item_formsets = EventPluginSignal(
    providing_args=['request', 'item']
)
"""
This signal allows you to return additional formsets that should be rendered on the product
modification page. You are passed ``request`` and ``item`` arguments and are expected to return
an instance of a formset class that you bind yourself when appropriate. Your formset will be
executed as part of the standard validation and rendering cycle and rendered using default
bootstrap styles. It is advisable to set a prefix for your formset to avoid clashes with other
plugins.

Your formset needs to have two special properties: ``template`` with a template that will be
included to render the formset and ``title`` that will be used as a headline. Your template
will be passed a ``formset`` variable with your formset.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

subevent_forms = EventPluginSignal(
    providing_args=['request', 'subevent']
)
"""
This signal allows you to return additional forms that should be rendered on the subevent creation
or modification page. You are passed ``request`` and ``subevent`` arguments and are expected to return
an instance of a form class that you bind yourself when appropriate. Your form will be executed
as part of the standard validation and rendering cycle and rendered using default bootstrap
styles. It is advisable to set a prefix for your form to avoid clashes with other plugins.

``subevent`` can be ``None`` during creation. Before ``save()`` is called, a ``subevent`` property of
your form instance will automatically being set to the subevent that has just been created.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

oauth_application_registered = Signal(
    providing_args=["user", "application"]
)
"""
This signal will be called whenever a user registers a new OAuth application.
"""

order_search_filter_q = Signal(
    providing_args=["query"]
)
"""
This signal will be called whenever a free-text order search is performed. You are expected to return one
Q object that will be OR-ed with existing search queries. As order search exists on a global level as well,
this is not an Event signal and will be called even if your plugin is not active. ``sender`` will contain the
event if the search is performed within an event, and ``None`` otherwise. The search query will be passed as
``query``.
"""
