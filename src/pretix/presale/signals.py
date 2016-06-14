from pretix.base.signals import EventPluginSignal

"""
This signal is sent out to include code into the HTML <head> tag
"""
html_head = EventPluginSignal(
    providing_args=["request"]
)

"""
This signal is sent out to include links in the footer
"""
footer_link = EventPluginSignal(
    providing_args=["request"]
)

"""
This signal is sent out to retrieve pages for the checkout flow
"""
checkout_flow_steps = EventPluginSignal()
