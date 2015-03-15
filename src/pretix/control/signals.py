from pretix.base.signals import EventPluginSignal


"""
This signal is sent out to build configuration forms for all restriction formsets
(see plugin API documentation for details).
"""
restriction_formset = EventPluginSignal(
    providing_args=["item"]
)

"""
This signal is sent out to include code into the HTML <head> tag
"""
html_head = EventPluginSignal(
    providing_args=[]
)
