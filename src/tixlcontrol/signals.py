from tixlbase.signals import EventPluginSignal


restriction_formset = EventPluginSignal(
    providing_args=["item"]
)
