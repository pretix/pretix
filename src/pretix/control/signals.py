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
    providing_args=["request"]
)

"""
This signal is sent out to include navigation items in the event admin
"""
nav_event = EventPluginSignal(
    providing_args=["request"]
)

"""
This signal is sent out to include widgets to the event dashboard. Receivers
should return a list of dictionaries, where each dictionary can have the keys:
* content (str, containing HTML)
* minimal width (int, widget width in 1/12ths of the page, default ist 3, can be
  ignored on small displays)
* priority (int, used for ordering, higher comes first, default is 1)
* link (str, optional, if the full widget should be a link)
"""
event_dashboard_widgets = EventPluginSignal(
    providing_args=[]
)
