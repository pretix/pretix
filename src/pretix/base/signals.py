#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze, Tobias Kunze, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import warnings
from typing import Any, Callable, List, Tuple

import django.dispatch
from django.apps import apps
from django.conf import settings
from django.dispatch.dispatcher import NO_RECEIVERS

from .models import Event

app_cache = {}


def _populate_app_cache():
    global app_cache
    apps.check_apps_ready()
    for ac in apps.app_configs.values():
        app_cache[ac.name] = ac


class EventPluginSignal(django.dispatch.Signal):
    """
    This is an extension to Django's built-in signals which differs in a way that it sends
    out it's events only to receivers which belong to plugins that are enabled for the given
    Event.
    """

    def _is_active(self, sender, receiver):
        if sender is None:
            # Send to all events!
            return True

        # If sentry packed this in a wrapper, unpack that
        if "sentry" in receiver.__module__:
            receiver = receiver.__wrapped__

        # Find the Django application this belongs to
        searchpath = receiver.__module__
        core_module = any([searchpath.startswith(cm) for cm in settings.CORE_MODULES])
        app = None
        if not core_module:
            while True:
                app = app_cache.get(searchpath)
                if "." not in searchpath or app:
                    break
                searchpath, _ = searchpath.rsplit(".", 1)

        # Only fire receivers from active plugins and core modules
        excluded = settings.PRETIX_PLUGINS_EXCLUDE
        if core_module or (sender and app and app.name in sender.get_plugins() and app.name not in excluded):
            if not hasattr(app, 'compatibility_errors') or not app.compatibility_errors:
                return True
        return False

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

        if not app_cache:
            _populate_app_cache()

        for receiver in self._sorted_receivers(sender):
            if self._is_active(sender, receiver):
                response = receiver(signal=self, sender=sender, **named)
                responses.append((receiver, response))
        return responses

    def send_chained(self, sender: Event, chain_kwarg_name, **named) -> List[Tuple[Callable, Any]]:
        """
        Send signal from sender to all connected receivers. The return value of the first receiver
        will be used as the keyword argument specified by ``chain_kwarg_name`` in the input to the
        second receiver and so on. The return value of the last receiver is returned by this method.

        sender is required to be an instance of ``pretix.base.models.Event``.
        """
        if sender and not isinstance(sender, Event):
            raise ValueError("Sender needs to be an event.")

        response = named.get(chain_kwarg_name)
        if not self.receivers or self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return response

        if not app_cache:
            _populate_app_cache()

        for receiver in self._sorted_receivers(sender):
            if self._is_active(sender, receiver):
                named[chain_kwarg_name] = response
                response = receiver(signal=self, sender=sender, **named)
        return response

    def send_robust(self, sender: Event, **named) -> List[Tuple[Callable, Any]]:
        """
        Send signal from sender to all connected receivers. If a receiver raises an exception
        instead of returning a value, the exception is included as the result instead of
        stopping the response chain at the offending receiver.

        sender is required to be an instance of ``pretix.base.models.Event``.
        """
        if sender and not isinstance(sender, Event):
            raise ValueError("Sender needs to be an event.")

        responses = []
        if (
            not self.receivers
            or self.sender_receivers_cache.get(sender) is NO_RECEIVERS
        ):
            return []

        if not app_cache:
            _populate_app_cache()

        for receiver in self._sorted_receivers(sender):
            if self._is_active(sender, receiver):
                try:
                    response = receiver(signal=self, sender=sender, **named)
                except Exception as err:
                    responses.append((receiver, err))
                else:
                    responses.append((receiver, response))
        return responses

    def _sorted_receivers(self, sender):
        orig_list = self._live_receivers(sender)
        sorted_list = sorted(
            orig_list,
            key=lambda receiver: (
                0 if any(receiver.__module__.startswith(m) for m in settings.CORE_MODULES) else 1,
                receiver.__module__,
                receiver.__name__,
            )
        )
        return sorted_list


class GlobalSignal(django.dispatch.Signal):
    def send_chained(self, sender: Event, chain_kwarg_name, **named) -> List[Tuple[Callable, Any]]:
        """
        Send signal from sender to all connected receivers. The return value of the first receiver
        will be used as the keyword argument specified by ``chain_kwarg_name`` in the input to the
        second receiver and so on. The return value of the last receiver is returned by this method.

        """
        response = named.get(chain_kwarg_name)
        if not self.receivers or self.sender_receivers_cache.get(sender) is NO_RECEIVERS:
            return response

        for receiver in self._live_receivers(sender):
            named[chain_kwarg_name] = response
            response = receiver(signal=self, sender=sender, **named)
        return response


class DeprecatedSignal(django.dispatch.Signal):

    def connect(self, receiver, sender=None, weak=True, dispatch_uid=None):
        warnings.warn('This signal is deprecated and will soon be removed', stacklevel=3)
        super().connect(receiver, sender=None, weak=True, dispatch_uid=None)


event_live_issues = EventPluginSignal()
"""
This signal is sent out to determine whether an event can be taken live. If you want to
prevent the event from going live, return a string that will be displayed to the user
as the error message. If you don't, your receiver should return ``None``.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""


register_payment_providers = EventPluginSignal()
"""
This signal is sent out to get all known payment providers. Receivers should return a
subclass of pretix.base.payment.BasePaymentProvider or a list of these

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_mail_placeholders = EventPluginSignal()
"""
This signal is sent out to get all known email text placeholders. Receivers should return
an instance of a subclass of pretix.base.email.BaseMailTextPlaceholder or a list of these.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_html_mail_renderers = EventPluginSignal()
"""
This signal is sent out to get all known HTML email renderers. Receivers should return a
subclass of pretix.base.email.BaseHTMLMailRenderer or a list of these

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_invoice_renderers = EventPluginSignal()
"""
This signal is sent out to get all known invoice renderers. Receivers should return a
subclass of pretix.base.invoice.BaseInvoiceRenderer or a list of these

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_ticket_secret_generators = EventPluginSignal()
"""
This signal is sent out to get all known ticket secret generators. Receivers should return a
subclass of ``pretix.base.secrets.BaseTicketSecretGenerator`` or a list of these

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_data_shredders = EventPluginSignal()
"""
This signal is sent out to get all known data shredders. Receivers should return a
subclass of pretix.base.shredder.BaseDataShredder or a list of these

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_ticket_outputs = EventPluginSignal()
"""
This signal is sent out to get all known ticket outputs. Receivers should return a
subclass of pretix.base.ticketoutput.BaseTicketOutput

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_notification_types = EventPluginSignal()
"""
This signal is sent out to get all known notification types. Receivers should return an
instance of a subclass of pretix.base.notifications.NotificationType or a list of such
instances.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event,
however for this signal, the ``sender`` **may also be None** to allow creating the general
notification settings!
"""

register_sales_channels = django.dispatch.Signal()
"""
This signal is sent out to get all known sales channels types. Receivers should return an
instance of a subclass of ``pretix.base.channels.SalesChannel`` or a list of such
instances.
"""

register_data_exporters = EventPluginSignal()
"""
This signal is sent out to get all known data exporters. Receivers should return a
subclass of pretix.base.exporter.BaseExporter

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

register_multievent_data_exporters = django.dispatch.Signal()
"""
Arguments: ``event``

This signal is sent out to get all known data exporters, which support exporting data for
multiple events. Receivers should return a subclass of pretix.base.exporter.BaseExporter

The ``sender`` keyword argument will contain an organizer.
"""

validate_order = EventPluginSignal()
"""
Arguments: ``payments``, ``positions``, ``email``, ``locale``, ``invoice_address``,
``meta_info``, ``customer``

This signal is sent out when the user tries to confirm the order, before we actually create
the order. It allows you to inspect the cart positions. Your return value will be ignored,
but you can raise an OrderError with an appropriate exception message if you like to block
the order. We strongly discourage making changes to the order here.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.

**DEPRECTATION:** Stop listening to the ``payment_provider`` attribute, it will be removed
in the future, as the ``payments`` attribute gives more information.
"""

order_valid_if_pending = EventPluginSignal()
"""
Arguments: ``payments``, ``positions``, ``email``, ``locale``, ``invoice_address``,
``meta_info``, ``customer``

This signal is sent out when the user tries to confirm the order, before we actually create
the order. It allows you to set the ``valid_if_pending`` of the order even before it is
created. Whenever any plugin returns ``True``, the order will be valid if pending.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

validate_cart = EventPluginSignal()
"""
Arguments: ``positions``

This signal is sent out before the user starts checkout. It includes an iterable
with the current CartPosition objects.
The response of receivers will be ignored, but you can raise a CartError with an
appropriate exception message.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

validate_cart_addons = EventPluginSignal()
"""
Arguments: ``addons``, ``base_position``, ``iao``

This signal is sent when a user tries to select a combination of addons. In contrast to
 ``validate_cart``, this is executed before the cart is actually modified. You are passed
an argument ``addons`` containing a dict of ``(item, variation or None) → count`` tuples as well
as the ``ItemAddOn`` object as the argument ``iao`` and the base cart position as
``base_position``.
The response of receivers will be ignored, but you can raise a CartError with an
appropriate exception message.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_placed = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is placed. The order object is given
as the first argument. This signal is *not* sent out if an order is created through
splitting an existing order, so you can not expect to see all orders by listening
to this signal.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_paid = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is paid. The order object is given
as the first argument. This signal is *not* sent out if an order is marked as paid
because an already-paid order has been split.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_canceled = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is canceled. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_reactivated = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time a canceled order is reactivated. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_expired = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is marked as expired. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_modified = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order's information is modified. The order object is given
as the first argument. In contrast to ``order_changed``, this signal is sent out if information
of an order or any of it's position is changed that concerns user input, such as attendee names,
invoice addresses or question answers. If the order changes in a material way, such as changed
products, prices, or tax rates, ``order_changed`` is used instead.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_changed = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order's content is changed. The order object is given
as the first argument. In contrast to ``modified``, this signal is sent out if the order or
any of its positions changes in a material way, such as changed products, prices, or tax rates,
``order_changed`` is used instead. If "only" user input is changed, such as attendee names,
invoice addresses or question answers, ``order_modified`` is used instead.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_approved = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is being approved. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_denied = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time an order is being denied. The order object is given
as the first argument.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

order_gracefully_delete = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out every time a test-mode order is being deleted. The order object
is given as the first argument.

Any plugin receiving this signals is supposed to perform any cleanup necessary at this
point, so that the underlying order has no more external constraints that would inhibit
the deletion of the order.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

checkin_created = EventPluginSignal()
"""
Arguments: ``checkin``

This signal is sent out every time a check-in is created (i.e. an order position is marked as
checked in). It is not send if the position was already checked in and is force-checked-in a second time.
The check-in object is given as the first argument.

For backwards compatibility reasons, this signal is only sent when a **successful** scan is saved.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

logentry_display = EventPluginSignal()
"""
Arguments: ``logentry``

To display an instance of the ``LogEntry`` model to a human user,
``pretix.base.signals.logentry_display`` will be sent out with a ``logentry`` argument.

The first received response that is not ``None`` will be used to display the log entry
to the user. The receivers are expected to return plain text.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

logentry_object_link = EventPluginSignal()
"""
Arguments: ``logentry``

To display the relationship of an instance of the ``LogEntry`` model to another model
to a human user, ``pretix.base.signals.logentry_object_link`` will be sent out with a
``logentry`` argument.

The first received response that is not ``None`` will be used to display the related object
to the user. The receivers are expected to return a HTML link. The internal implementation
builds the links like this::

    a_text = _('Tax rule {val}')
    a_map = {
        'href': reverse('control:event.settings.tax.edit', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug,
            'rule': logentry.content_object.id
        }),
        'val': escape(logentry.content_object.name),
    }
    a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
    return a_text.format_map(a_map)

Make sure that any user content in the HTML code you return is properly escaped!
As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

requiredaction_display = EventPluginSignal()
"""
**DEPRECATED**, will no longer be called.
"""

event_copy_data = EventPluginSignal()
"""
Arguments: "other", ``tax_map``, ``category_map``, ``item_map``, ``question_map``, ``variation_map``, ``checkin_list_map``, ``quota_map``

This signal is sent out when a new event is created as a clone of an existing event, i.e.
the settings from the older event are copied to the newer one. You can listen to this
signal to copy data or configuration stored within your plugin's models as well.

You don't need to copy data inside the general settings storage which is cloned automatically,
but you might need to modify that data.

The ``sender`` keyword argument will contain the event of the **new** event. The ``other``
keyword argument will contain the event to **copy from**. The keyword arguments
``tax_map``, ``category_map``, ``item_map``, ``question_map``, ``quota_map``, ``variation_map`` and
``checkin_list_map`` contain mappings from object IDs in the original event to objects
in the new event of the respective types.
"""

orderposition_blocked_display = EventPluginSignal()
"""
Arguments: ``orderposition``, ``block_name``

To display the reason for a blocked ticket to a backend user,
``pretix.base.signals.orderposition_block_display`` will be sent out.

The first received response that is not ``None`` will be used to display the block
to the user. The receivers are expected to return plain text.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

item_copy_data = EventPluginSignal()
"""
Arguments: ``source``, ``target``

This signal is sent out when a new product is created as a clone of an existing product, i.e.
the settings from the older product are copied to the newer one. You can listen to this
signal to copy data or configuration stored within your plugin's models as well.

The ``sender`` keyword argument will contain the event. The ``target`` will contain the item to
copy to, the ``source`` keyword argument will contain the product to **copy from**.
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

gift_card_transaction_display = django.dispatch.Signal()
"""
Arguments: ``transaction``, ``customer_facing``

To display an instance of the ``GiftCardTransaction`` model to a human user,
``pretix.base.signals.gift_card_transaction_display`` will be sent out with a ``transaction`` argument.
The ``customer_facing`` argument specifies whether the HTML will be shown to an end-user or if it is being
used in the backend.

The first received response that is not ``None`` will be used to display the log entry
to the user. The receivers are expected to return a string (that might be marked with ``mark_safe`` from Django if
it contains HTML).
"""

order_fee_calculation = EventPluginSignal()
"""
Arguments: ``positions``, ``invoice_address``, ``meta_info``, ``total``, ``gift_cards``, ``payment_requests``

This signals allows you to add fees to an order while it is being created. You are expected to
return a list of ``OrderFee`` objects that are not yet saved to the database
(because there is no order yet).

As with all plugin signals, the ``sender`` keyword argument will contain the event. A ``positions``
argument will contain the cart positions and ``invoice_address`` the invoice address (useful for
tax calculation). The argument ``meta_info`` contains the order's meta dictionary. The ``total``
keyword argument will contain the total cart sum without any fees. You should not rely on this
``total`` value for fee calculations as other fees might interfere. The ``gift_cards`` argument
lists the gift cards in use.

**DEPRECTATION:** Stop listening to the ``gift_cards`` attribute, it will be removed in the future.
"""

order_fee_type_name = EventPluginSignal()
"""
Arguments: ``request``, ``fee``

This signals allows you to return a human-readable description for a fee type based on the ``fee_type``
and ``internal_type`` attributes of the ``OrderFee`` model that you get as keyword arguments. You are
expected to return a string or None, if you don't know about this fee.

As with all plugin signals, the ``sender`` keyword argument will contain the event.
"""

allow_ticket_download = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out to check if tickets for an order can be downloaded. If any receiver returns false,
a download will not be offered.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

email_filter = EventPluginSignal()
"""
Arguments: ``message``, ``order``, ``user``

This signal allows you to implement a middleware-style filter on all outgoing emails. You are expected to
return a (possibly modified) copy of the message object passed to you.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
The ``message`` argument will contain an ``EmailMultiAlternatives`` object.
If the email is associated with a specific order, the ``order`` argument will be passed as well, otherwise
it will be ``None``.
If the email is associated with a specific user, e.g. a notification email, the ``user`` argument will be passed as
well, otherwise it will be ``None``.
"""

global_email_filter = GlobalSignal()
"""
Arguments: ``message``, ``order``, ``user``, ``customer``, ``organizer``

This signal allows you to implement a middleware-style filter on all outgoing emails. You are expected to
return a (possibly modified) copy of the message object passed to you.

This signal is called on all events and even if there is no known event. ``sender`` is an event or None.
The ``message`` argument will contain an ``EmailMultiAlternatives`` object.
If the email is associated with a specific order, the ``order`` argument will be passed as well, otherwise
it will be ``None``.
If the email is associated with a specific user, e.g. a notification email, the ``user`` argument will be passed as
well, otherwise it will be ``None``.
"""


layout_text_variables = EventPluginSignal()
"""
This signal is sent out to collect variables that can be used to display text in ticket-related PDF layouts.
Receivers are expected to return a dictionary with globally unique identifiers as keys and more
dictionaries as values that contain keys like in the following example::

    return {
        "product": {
            "label": _("Product name"),
            "editor_sample": _("Sample product"),
            "evaluate": lambda orderposition, order, event: str(orderposition.item)
        }
    }

The ``evaluate`` member will be called with the order position, order and event as arguments. The event might
also be a subevent, if applicable.
"""


layout_image_variables = EventPluginSignal()
"""
This signal is sent out to collect variables that can be used to display dynamic images in ticket-related PDF layouts.
Receivers are expected to return a dictionary with globally unique identifiers as keys and more
dictionaries as values that contain keys like in the following example::

    return {
        "profile": {
            "label": _("Profile picture"),
            "evaluate": lambda orderposition, order, event: ContentFile(b"some-image-data"),
            "etag": lambda orderposition, order, event: hash(b"some-image-data")
        }
    }

The ``evaluate`` member will be called with the order position, order and event as arguments. The event might
also be a subevent, if applicable. The return value of ``evaluate`` should be an instance of Django's ``File``
class and point to a valid JPEG or PNG file. If no image is available, ``evaluate`` should return ``None``.

The ``etag`` member will be called with the same arguments as ``evaluate`` but should return a ``str`` value
uniquely identifying the version of the file. This can be a hash of the file, but can also be something else.
If no image is available, ``etag`` should return ``None``. In some cases, this can speed up the implementation.
"""


timeline_events = EventPluginSignal()
"""
This signal is sent out to collect events for the time line shown on event dashboards. You are passed
a ``subevent`` argument which might be none and you are expected to return a list of instances of
``pretix.base.timeline.TimelineEvent``, which is a ``namedtuple`` with the fields ``event``, ``subevent``,
``datetime``, ``description`` and ``edit_url``.
"""


quota_availability = EventPluginSignal()
"""
Arguments: ``quota``, ``result``, ``count_waitinglist``

This signal allows you to modify the availability of a quota. You are passed the ``quota`` and an
``availability`` result calculated by pretix code or other plugins. ``availability`` is a tuple
with the first entry being one of the ``Quota.AVAILABILITY_*`` constants and the second entry being
the number of available tickets (or ``None`` for unlimited). You are expected to return a value
of the same type. The parameter ``count_waitinglists`` specifies whether waiting lists should be taken
into account.

**Warning: Use this signal with great caution, it allows you to screw up the performance of the
system really bad.** Also, keep in mind that your response is subject to caching and out-of-date
quotas might be used for display (not for actual order processing).
"""

order_split = EventPluginSignal()
"""
Arguments: ``original``, ``split_order``

This signal is sent out when an order is split into two orders and allows you to copy related models
to the new order. You will be passed the old order as ``original`` and the new order as ``split_order``.
"""

invoice_line_text = EventPluginSignal()
"""
Arguments: ``position``

This signal is sent out when an invoice is built for an order. You can return additional text that
should be shown on the invoice for the given ``position``.
"""

order_import_columns = EventPluginSignal()
"""
This signal is sent out if the user performs an import of orders from an external source. You can use this
to define additional columns that can be read during import. You are expected to return a list of instances of
``ImportColumn`` subclasses.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

validate_event_settings = EventPluginSignal()
"""
Arguments: ``settings_dict``

This signal is sent out if the user performs an update of event settings through the API or web interface.
You are passed a ``settings_dict`` dictionary with the new state of the event settings object and are expected
to raise a ``django.core.exceptions.ValidationError`` if the new state is not valid.
You can not modify the dictionary. This is only recommended to use if you have multiple settings
that can only be validated together. To validate individual settings, pass a validator to the
serializer field instead.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

api_event_settings_fields = EventPluginSignal()
"""
This signal is sent out to collect serializable settings fields for the API. You are expected to
return a dictionary mapping names of attributes in the settings store to DRF serializer field instances.

As with all event-plugin signals, the ``sender`` keyword argument will contain the event.
"""

customer_created = GlobalSignal()
"""
Arguments: ``customer``

This signal is sent out every time a customer account is created. The ``customer``
object is given as the first argument.

The ``sender`` keyword argument will contain the organizer.
"""

customer_signed_in = GlobalSignal()
"""
Arguments: ``customer``

This signal is sent out every time a customer signs in. The ``customer`` object
is given as the first argument.

The ``sender`` keyword argument will contain the organizer.
"""
