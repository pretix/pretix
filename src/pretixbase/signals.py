import django.dispatch
from django.apps import apps
from django.dispatch.dispatcher import NO_RECEIVERS

from .models import Event


class EventPluginSignal(django.dispatch.Signal):
    """
    This is an extension to Django's built-in signals which differs in a way that it sends
    out it's events only to receivers which belong to plugins that are enabled for the given
    Event.
    """

    def send(self, sender, **named):
        """
        Send signal from sender to all connected receivers that belong to
        plugins enabled for the given Event.

        sender is required to be an instance of ``pretixbase.models.Event``.
        """
        assert isinstance(sender, Event)

        responses = []
        if not self.receivers or self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return responses

        for receiver in self._live_receivers(sender):
            # Find the Django application this belongs to
            searchpath = receiver.__module__
            app = None
            while "." in searchpath:
                try:
                    if apps.is_installed(searchpath):
                        app = apps.get_app_config(searchpath.split(".")[-1])
                except LookupError:
                    pass
                searchpath, mod = searchpath.rsplit(".", 1)

            # Only fire receivers from active plugins
            if app.name in sender.get_plugins():
                response = receiver(signal=self, sender=sender, **named)
                responses.append((receiver, response))
        return responses

"""
This signal is sent out every time some component of pretix wants to know whether a specific
item or variation is available for sell. The item will only be sold, if all (active) receivers
return a positive result (see plugin API documentation for details).
"""
determine_availability = EventPluginSignal(
    providing_args=["item", "variations", "context", "cache"]
)
