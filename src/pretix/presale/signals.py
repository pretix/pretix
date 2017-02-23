from pretix.base.signals import EventPluginSignal

html_head = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal allows you to put code inside the HTML ``<head>`` tag
of every page in the frontend. You will get the request as the keyword argument
``request`` and are expected to return plain HTML.

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

checkout_confirm_messages = EventPluginSignal()
"""
This signal is sent out to retrieve short messages that need to be acknowledged by the user before the
order can be completed. This is typically used for something like "accept the terms and conditions".
Receivers are expected to return a dictionary where the keys are globally unique identifiers for the
message and the values can be arbitrary HTML.

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

order_meta_from_request = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal is sent before an order is created through the pretixpresale frontend. It allows you
to return a dictionary that will be merged in the meta_info attribute of the order.
You will recieve the request triggering the order creation as the ``request`` keyword argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_info = EventPluginSignal(
    providing_args=["order"]
)
"""
This signal is sent out to display additional information on the order detail page

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

process_request = EventPluginSignal(
    providing_args=["request"]
)
"""
This signal is sent out whenever a request is made to a event presale page. Most of the
time, this will be called from the middleware layer (except on plugin-provided pages
this will be called by the @event_view decorator). Similarly to Django's process_request
middleware method, if you return a Response, that response will be used and the request
won't be processed any further down the stack.

WARNING: Be very careful about using this signal as listening to it makes it really
easy to cause serious performance problems.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

process_response = EventPluginSignal(
    providing_args=["request", "response"]
)
"""
This signal is sent out whenever a response is sent from a event presale page. Most of
the time, this will be called from the middleware layer (except on plugin-provided pages
this will be called by the @event_view decorator). Similarly to Django's process_response
middleware method you must return a response object, that will be passed further up the
stack to other handlers of the signal. If you do not want to alter the response, just
return the ``response`` parameter.

WARNING: Be very careful about using this signal as listening to it makes it really
easy to cause serious performance problems.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

front_page_top = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to display additional information on the frontpage above the list
of products and but below a custom frontpage text.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""

front_page_bottom = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to display additional information on the frontpage below the list
of products.

As with all plugin signals, the ``sender`` keyword argument will contain the event. The
receivers are expected to return HTML.
"""
