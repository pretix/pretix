from pretix.base.signals import EventPluginSignal


"""
This signal is sent out to include code into the HTML <head> tag
"""
html_head = EventPluginSignal(
    providing_args=["request"]
)
