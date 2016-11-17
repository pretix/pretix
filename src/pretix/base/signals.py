from typing import Any, Callable, List, Tuple

import django.dispatch
from django.apps import apps
from django.conf import settings
from django.dispatch.dispatcher import NO_RECEIVERS

from .models import Event


class EventPluginSignal(django.dispatch.Signal):
    """
    This is an extension to Django's built-in signals which differs in a way that it sends
    out it's events only to receivers which belong to plugins that are enabled for the given
    Event.
    """

    def send(self, sender: Event, **named) -> List[Tuple[Callable, Any]]:
        """
        Send signal from sender to all connected receivers that belong to
        plugins enabled for the given Event.

        sender is required to be an instance of ``pretix.base.models.Event``.
        """
        if sender and not isinstance(sender, Event):
            raise ValueError("Sender needs to be an event.")

        responses = []
        if not self.receivers or self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return responses

        for receiver in self._live_receivers(sender):
            # Find the Django application this belongs to
            searchpath = receiver.__module__
            app = None
            mod = None
            while True:
                try:
                    if apps.is_installed(searchpath):
                        app = apps.get_app_config(searchpath.split(".")[-1])
                except LookupError:
                    pass
                if "." not in searchpath:
                    break
                searchpath, mod = searchpath.rsplit(".", 1)

            # Only fire receivers from active plugins and core modules
            if (searchpath, mod) in settings.CORE_MODULES or (sender and app and app.name in sender.get_plugins()):
                if not hasattr(app, 'compatibility_errors') or not app.compatibility_errors:
                    response = receiver(signal=self, sender=sender, **named)
                    responses.append((receiver, response))
        return responses


register_payment_providers = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to get all known payment providers. Receivers should return a
subclass of pretix.base.payment.BasePaymentProvider

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_ticket_outputs = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to get all known ticket outputs. Receivers should return a
subclass of pretix.base.ticketoutput.BaseTicketOutput

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_data_exporters = EventPluginSignal(
    providing_args=[]
)
"""
This signal is sent out to get all known data exporters. Receivers should return a
subclass of pretix.base.exporter.BaseExporter

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_placed = EventPluginSignal(
    providing_args=["order"]
)
"""
This signal is sent out every time an order is placed. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_paid = EventPluginSignal(
    providing_args=["order"]
)
"""
This signal is sent out every time an order is paid. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

logentry_display = EventPluginSignal(
    providing_args=["logentry"]
)
"""
To display an instance of the ``LogEntry`` model to a human user,
``pretix.base.signals.logentry_display`` will be sent out with a ``logentry`` argument.

The first received response that is not ``None`` will be used to display the log entry
to the user.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

periodic_task = django.dispatch.Signal()
"""
This is a regular django signal (no pretix event signal) that we send out every
time the periodic task cronjob runs. This interval is not sharply defined, it can
be everything between a minute and a day. The actions you perform should be
idempotent, i.e. it should not make a difference if this is sent out more often
than expected.
"""

register_global_settings = django.dispatch.Signal()
"""
All plugins that are installed may send fields for the global settings form, as
an OrderedDict of (setting name, form field).
"""
