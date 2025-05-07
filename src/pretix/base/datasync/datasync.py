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

import json
import logging
from collections import namedtuple
from datetime import timedelta
from functools import cached_property
from itertools import groupby

import sentry_sdk
from django.db.models import Q
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.datasync.sourcefields import (
    EVENT, EVENT_OR_SUBEVENT, ORDER, ORDER_POSITION, get_data_fields,
)
from pretix.base.logentrytype_registry import make_link
from pretix.base.models.datasync import OrderSyncQueue, OrderSyncResult
from pretix.base.signals import EventPluginRegistry, periodic_task
from pretix.celery_app import app

logger = logging.getLogger(__name__)


@receiver(periodic_task, dispatch_uid="data_sync_periodic")
def on_periodic_task(sender, **kwargs):
    sync_all.apply_async()


sync_targets = EventPluginRegistry({"identifier": lambda o: o.identifier})


def sync_event_to_target(event, target_cls, queued_orders):
    with scope(organizer=event.organizer):
        with target_cls(event=event) as p:
            # TODO: should I somehow lock the queued orders or events, to avoid syncing them twice at the same time?
            p.sync_queued_orders(queued_orders)


@app.task()
def sync_all():
    with scopes_disabled():
        queue = (
            OrderSyncQueue.objects
            .select_related("order")
            .prefetch_related("order__event")
            .filter(Q(not_before__isnull=True) | Q(not_before__lt=now()))[:1000]
        )
        grouped = groupby(sorted(queue, key=lambda q: (q.sync_provider, q.order.event.pk)), lambda q: (q.sync_provider, q.order.event))
        for (target, event), queued_orders in grouped:
            target_cls, meta = sync_targets.get(identifier=target, active_in=event)

            if not target_cls:
                # sync plugin not found (plugin deactivated or uninstalled) -> drop outstanding jobs
                for sq in queued_orders:
                    sq.delete()

            sync_event_to_target(event, target_cls, queued_orders)


class BaseSyncError(Exception):
    def __init__(self, messages, full_message=None):
        self.messages = messages
        self.full_message = full_message


class UnrecoverableSyncError(BaseSyncError):
    """
    A SyncProvider encountered a permanent problem, where a retry will not be successful.
    """
    log_action_type = "pretix.event.order.data_sync.failed.permanent"


class SyncConfigError(UnrecoverableSyncError):
    """
    A SyncProvider is misconfigured in a way where a retry without configuration change will
    not be successful.
    """
    log_action_type = "pretix.event.order.data_sync.failed.config"


class RecoverableSyncError(BaseSyncError):
    """
    A SyncProvider has encountered a temporary problem, and the sync should be retried
    at a later time.
    """
    pass


StaticMapping = namedtuple('StaticMapping', ('pk', 'pretix_model', 'external_object_type', 'pretix_id_field', 'external_id_field', 'property_mapping'))


class OutboundSyncProvider:
    max_attempts = 5

    def __init__(self, event):
        self.event = event

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @classmethod
    @property
    def display_name(cls):
        return str(cls.identifier)

    @classmethod
    def enqueue_order(cls, order, triggered_by, not_before=None):
        """
        Adds an order to the sync queue. May only be called on derived classes which define an ``identifier`` attribute.

        Should be called in the appropriate signal receivers, e.g.::

            @receiver(order_placed, dispatch_uid="mysync_order_placed")
            def on_order_placed(sender, order, **kwargs):
                MySyncProvider.enqueue_order(order, "order_placed")

        :param order: the Order that should be synced
        :param triggered_by: the reason why the order should be synced, e.g. name of the signal
                             (currently only used internally for logging)
        """
        if not hasattr(cls, 'identifier'):
            raise TypeError('Call this method on a derived class that defines an "identifier" attribute.')
        OrderSyncQueue.objects.create(
            order=order,
            event=order.event,
            sync_provider=cls.identifier,
            triggered_by=triggered_by,
            not_before=not_before or now(),
        )

    @classmethod
    def get_external_link_info(cls, event, external_link_href, external_link_display_name):
        return {
            "href": external_link_href,
            "val": external_link_display_name,
        }

    @classmethod
    def get_external_link_html(cls, event, external_link_href, external_link_display_name):
        info = cls.get_external_link_info(event, external_link_href, external_link_display_name)
        return make_link(info, '{val}')

    def next_retry_date(self, sq):
        """
        Optionally override to configure a different retry backoff behavior
        """
        return now() + timedelta(hours=1)

    def order_valid_for_sync(self, order):
        """
        Optionally override this method to exclude certain orders from sync by returning ``False``
        """
        return True

    @property
    def mappings(self):
        """
        Implementations must override this property to provide the data mappings as a list of objects.

        They can return instances of the ``StaticMapping`` `namedtuple` defined above, or create their own
        class (e.g. a Django model).

        :return: The returned objects must have at least the following properties:

                - `pk`: Unique identifier
                - `pretix_model`: Which pretix model to use as data source in this mapping. Possible values are
                  the keys of ``sourcefields.AVAILABLE_MODELS``
                - `external_object_type`: Destination object type in the target system. opaque string of maximum 128 characters.
                - `pretix_id_field`: Which pretix data field should be used to identify the mapped object. Any ``DataFieldInfo.key``
                  returned by ``sourcefields.get_data_fields()`` for the combination of ``Event`` and ``pretix_model``.
                - `external_id_field`: Destination identifier field in the target system.
                - `property_mapping`: Mapping configuration as generated by ``PropertyMappingFormSet.to_property_mapping_json()``.
        """
        raise NotImplementedError

    def sync_queued_orders(self, queued_orders):
        for sq in queued_orders:
            try:
                mapped_objects = self.sync_order(sq.order)
            except UnrecoverableSyncError as e:
                logger.warning(
                    f"Could not sync order {sq.order.code} to {type(self).__name__}",
                    exc_info=True,
                )
                sq.order.log_action(e.log_action_type, {
                    "provider": self.identifier,
                    "error": e.messages,
                    "full_message": e.full_message,
                })
                sq.delete()
            except RecoverableSyncError as e:
                sq.failed_attempts += 1
                sq.not_before = self.next_retry_date(sq)
                logger.info(
                    f"Could not sync order {sq.order.code} to {type(self).__name__} (transient error, attempt #{sq.failed_attempts})",
                    exc_info=True,
                )
                if sq.failed_attempts >= self.max_attempts:
                    sentry_sdk.capture_exception(e)
                    sq.order.log_action("pretix.event.order.data_sync.failed.exceeded", {
                        "provider": self.identifier,
                        "error": e.messages,
                        "full_message": e.full_message,
                    })
                    sq.delete()
                else:
                    sq.save()
            except Exception as e:
                logger.exception(
                    f"Could not sync order {sq.order.code} to {type(self).__name__} (unhandled exception)"
                )
                sentry_sdk.capture_exception(e)
                sq.order.log_action("pretix.event.order.data_sync.failed.internal", {
                    "provider": self.identifier,
                    "error": [],
                    "full_message": str(e),
                })
                sq.delete()
            else:
                sq.order.log_action("pretix.event.order.data_sync.success", {
                    "provider": self.identifier,
                    "objects": mapped_objects
                })
                sq.delete()

    @cached_property
    def data_fields(self):
        return {
            f.key: (f.required_input, f.label, f.type, f.enum_opts, f.getter)
            for f in get_data_fields(self.event)
        }

    def get_field_value(self, inputs, mapping_entry):
        key = mapping_entry["pretix_field"]
        try:
            required_input, label, ptype, enum_opts, getter = self.data_fields[key]
        except KeyError:
            raise SyncConfigError(['Field "%s" is not valid for %s. Please check your %s settings.' % (key, "/".join(inputs.keys()), self.display_name)])
        input = inputs[required_input]
        val = getter(input)
        if isinstance(val, list):
            if enum_opts and mapping_entry.get("value_map"):
                map = json.loads(mapping_entry["value_map"])
                try:
                    val = [map[el] for el in val]
                except KeyError:
                    raise SyncConfigError([f'Please update value mapping for field "{key}" - option "{val}" not assigned'])

            val = ",".join(val)
        return val

    def get_properties(self, inputs: dict, property_mapping: str):
        property_mapping = json.loads(property_mapping)
        return [
            (m["external_field"], self.get_field_value(inputs, m), m["overwrite"])
            for m in property_mapping
        ]

    def sync_object_with_properties(
            self,
            external_id_field,
            id_value,
            properties: list,
            inputs: dict,
            mapping,
            mapped_objects: dict,
            **kwargs,
    ):
        """
        This method is called for each object that needs to be created/updated in the external system -- which these are is
        determined by the implementation of the `mapping` property.

        :param external_id_field: Identifier field in the external system as provided in ``mapping.external_identifier``
        :param id_value: Identifier contents as retrieved from the property specified by ``mapping.pretix_identifier`` of the model
                         specified by ``mapping.pretix_model``
        :param properties: All properties defined in ``mapping.property_mapping``, as list of three-tuples
                           ``(external_field, value, overwrite)``
        :param inputs: All pretix model instances from which data can be retrieved for this mapping
        :param mapping: The mapping object as returned by ``self.mappings``
        :param mapped_objects: Information about objects that were synced in the same sync run, by mapping definitions
                               *before* the current one in order of ``self.mappings``.
                               Type is a dictionary ``{mapping.pk: [list of return values of this method]}``
                               Useful to create associations between objects in the target system.

        Example code to create return value::

                 return {
                    # required:
                    "object_type": mapping.external_object_type,
                    "external_id_field": external_id_field,
                    "id_value": id_value,

                    # optional:
                    "external_link_href": "https://external-system.example.com/backend/link/to/contact/123/",
                    "external_link_display_name": "Contact #123 - Jane Doe",
                    "...optionally further values you need in mapped_objects for association": 123456789,
                 }

        This method needs to be idempotent, i.e. calling it multiple times with the same input values should create
        only a single object in the target system.

        Subsequent calls with the same mapping and pk_value should update the existing object, instead of creating a new one.
        In a SQL database, you might use an `INSERT OR UPDATE` or `UPSERT` statement; many REST APIs provide an equivalent API call.
        """
        raise NotImplementedError()

    def sync_object(
            self,
            inputs: dict,
            mapping,
            mapped_objects: dict,
    ):
        logger.debug("Syncing object %r, %r, %r", inputs, mapping, mapped_objects)
        properties = self.get_properties(inputs, mapping.property_mapping)
        logger.debug("Properties: %r", properties)

        id_value = self.get_field_value(inputs, {"pretix_field": mapping.pretix_id_field})
        if not id_value:
            return None

        info = self.sync_object_with_properties(
            external_id_field=mapping.external_id_field,
            id_value=id_value,
            properties=properties,
            inputs=inputs,
            mapping=mapping,
            mapped_objects=mapped_objects,
        )
        OrderSyncResult.objects.create(
            order=inputs.get(ORDER), order_position=inputs.get(ORDER_POSITION), sync_provider=self.identifier,
            external_object_type=info.get('object_type'),
            external_id_field=info.get('external_id_field'),
            id_value=info.get('id_value'),
            external_link_href=info.get('external_link_href'),
            external_link_display_name=info.get('external_link_display_name'),
        )
        return info

    def sync_order(self, order):
        if not self.order_valid_for_sync(order):
            logger.debug("Skipping order %r (not valid for sync)", order)
            return

        logger.debug("Syncing order %r", order)
        positions = list(
            order.all_positions
            .prefetch_related("answers", "answers__question")
            .select_related(
                "voucher",
            )
        )
        order.sync_results.filter(sync_provider=self.identifier).delete()
        order_inputs = {ORDER: order, EVENT: self.event}
        mapped_objects = {}
        for mapping in self.mappings:
            if mapping.pretix_model == 'Order':
                mapped_objects[mapping.pk] = [
                    self.sync_object(order_inputs, mapping, mapped_objects)
                ]
            elif mapping.pretix_model == 'OrderPosition':
                mapped_objects[mapping.pk] = [
                    self.sync_object({
                        **order_inputs, EVENT_OR_SUBEVENT: op.subevent or self.event, ORDER_POSITION: op
                    }, mapping, mapped_objects)
                    for op in positions
                ]
            else:
                raise SyncConfigError("Invalid pretix model '{}'".format(mapping.pretix_model))
        self.finalize_sync_order(order)
        return mapped_objects

    def finalize_sync_order(self, order):
        """
        Called after ``sync_object`` has been called successfully for all objects of a specific order. Can
        be used for saving bulk information per order.
        """
        pass

    def close(self):
        """
        Called after all orders of an event have been synced. Can be used for clean-up tasks (e.g. closing
        a session).
        """
        pass
