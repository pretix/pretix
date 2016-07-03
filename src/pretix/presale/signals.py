from pretix.base.signals import EventPluginSignal

html_head = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal allows you to put code inside the HTML ``<head>`` tag
of every page in the frontend. You will get the request as a keyword argument
``request`` and can return plain HTML.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

footer_link = EventPluginSignal(
    providing_args=["request"]
)
"""
The signal ``pretix.presale.signals.footer_links`` allows you to add links to the footer of an event page. You
are expected to return a dictionary containing the keys ``label`` and ``url``.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

checkout_flow_steps = EventPluginSignal()
"""
This signal is sent out to retrieve pages for the checkout flow

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

voucher_redeem_info = EventPluginSignal(
    providing_args=["voucher"]
)
"""
This signal is sent out to display additional information on the "redeem a voucher" page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""
