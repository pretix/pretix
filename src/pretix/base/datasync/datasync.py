#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from typing import List, Optional, Protocol

import sentry_sdk
from django.db import DatabaseError, transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretix.base.datasync.sourcefields import (
    EVENT, EVENT_OR_SUBEVENT, ORDER, ORDER_POSITION, get_data_fields,
)
from pretix.base.i18n import language
from pretix.base.logentrytype_registry import make_link
from pretix.base.models.datasync import OrderSyncQueue, OrderSyncResult
from pretix.base.signals import PluginAwareRegistry
from pretix.helpers import OF_SELF

logger = logging.getLogger(__name__)


datasync_providers = PluginAwareRegistry({"identifier": lambda o: o.identifier})


class BaseSyncError(Exception):
    def __init__(self, messages, full_message=None):
        self.messages = messages
        self.full_message = full_message


class UnrecoverableSyncError(BaseSyncError):
    """
    A SyncProvider encountered a permanent problem, where a retry will not be successful.
    """
    failure_mode = "permanent"


class SyncConfigError(UnrecoverableSyncError):
    """
    A SyncProvider is misconfigured in a way where a retry without configuration change will
    not be successful.
    """
    failure_mode = "config"


class RecoverableSyncError(BaseSyncError):
    """
    A SyncProvider has encountered a temporary problem, and the sync should be retried
    at a later time.
    """
    pass


class ObjectMapping(Protocol):
    id: int
    pretix_model: str
    external_object_type: str
    pretix_id_field: str
    external_id_field: str
    property_mappings: str


StaticMapping = namedtuple('StaticMapping', ('id', 'pretix_model', 'external_object_type', 'pretix_id_field', 'external_id_field', 'property_mappings'))


class OutboundSyncProvider:
    max_attempts = 5
    list_field_joiner = ","  # set to None to keep native lists in properties

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
    def enqueue_order(cls, order, triggered_by, not_before=None, immediate=False):
        """
        Adds an order to the sync queue. May only be called on derived classes which define an ``identifier`` attribute.

        Should be called in the appropriate signal receivers, e.g.::

            @receiver(order_placed, dispatch_uid="mysync_order_placed")
            def on_order_placed(sender, order, **kwargs):
                MySyncProvider.enqueue_order(order, "order_placed")

        :param order: the Order that should be synced
        :param triggered_by: the reason why the order should be synced, e.g. name of the signal
                             (currently only used internally for logging)
        :param immediate: whether a new sync task should run immediately for this order, instead
                          of waiting for the next periodic_task interval
        :return: Return a tuple (queue_item, created), where created is a boolean
                 specifying whether a new queue item was created.
        """
        if not hasattr(cls, 'identifier'):
            raise TypeError('Call this method on a derived class that defines an "identifier" attribute.')
        queue_item, created = OrderSyncQueue.objects.update_or_create(
            order=order,
            sync_provider=cls.identifier,
            in_flight=False,
            defaults={
                "event": order.event,
                "triggered_by": triggered_by,
                "not_before": not_before or now(),
                "need_manual_retry": None,
            },
        )
        if immediate:
            from pretix.base.services.datasync import sync_single
            sync_single.apply_async(args=(queue_item.pk,))
        return queue_item, created

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

    def should_sync_order(self, order):
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

                - `id`: Unique identifier for this mapping. If the mappings are Django models, the database primary key
                  should be used. This may be referenced in other mappings, to establish relations between objects.
                - `pretix_model`: Which pretix model to use as data source in this mapping. Possible values are
                  the keys of ``sourcefields.AVAILABLE_MODELS``
                - `external_object_type`: Destination object type in the target system. opaque string of maximum 128 characters.
                - `pretix_id_field`: Which pretix data field should be used to identify the mapped object. Any ``DataFieldInfo.key``
                  returned by ``sourcefields.get_data_fields()`` for the combination of ``Event`` and ``pretix_model``.
                - `external_id_field`: Destination identifier field in the target system.
                - `property_mappings`: Mapping configuration as generated by ``PropertyMappingFormSet.to_property_mappings_list()``.
        """
        raise NotImplementedError

    def sync_queued_orders(self, queued_orders):
        """
        This method should catch all Exceptions and handle them appropriately. It should never throw
        an Exception, as that may block the entire queue.
        """
        for queue_item in queued_orders:
            with transaction.atomic():
                try:
                    sq = (
                        OrderSyncQueue.objects
                        .select_for_update(of=OF_SELF, nowait=True)
                        .select_related("order")
                        .get(pk=queue_item.pk)
                    )
                    if sq.in_flight:
                        continue
                    sq.in_flight = True
                    sq.in_flight_since = now()
                    sq.save()
                except DatabaseError:
                    # Either select_for_update failed to lock the row, or we couldn't set in_flight
                    # as this order is already in flight (UNIQUE violation). In either case, we ignore
                    # this order for now.
                    continue

            try:
                mapped_objects = self.sync_order(sq.order)
                if not all(all(not res or res.sync_info.get("action", "") == "nothing_to_do" for res in res_list) for res_list in mapped_objects.values()):
                    sq.order.log_action("pretix.event.order.data_sync.success", {
                        "provider": self.identifier,
                        "objects": {
                            mapping_id: [osr and osr.to_result_dict() for osr in results]
                            for mapping_id, results in mapped_objects.items()
                        },
                    })
                sq.delete()
            except UnrecoverableSyncError as e:
                sq.set_sync_error(e.failure_mode, e.messages, e.full_message)
            except RecoverableSyncError as e:
                sq.failed_attempts += 1
                sq.not_before = self.next_retry_date(sq)
                # model changes saved by set_sync_error / clear_in_flight calls below
                if sq.failed_attempts >= self.max_attempts:
                    logger.exception('Failed to sync order (max attempts exceeded)')
                    sentry_sdk.capture_exception(e)
                    sq.set_sync_error("exceeded", e.messages, e.full_message)
                else:
                    logger.info(
                        f"Could not sync order {sq.order.code} to {type(self).__name__} "
                        f"(transient error, attempt #{sq.failed_attempts}, next {sq.not_before})",
                        exc_info=True,
                    )
                    sq.clear_in_flight()
            except Exception as e:
                logger.exception('Failed to sync order (unhandled exception)')
                sentry_sdk.capture_exception(e)
                sq.set_sync_error("internal", [], str(e))

    @cached_property
    def data_fields(self):
        return {
            f.key: f
            for f in get_data_fields(self.event)
        }

    def get_field_value(self, inputs, mapping_entry):
        key = mapping_entry["pretix_field"]
        try:
            field = self.data_fields[key]
        except KeyError:
            with language(self.event.settings.locale):
                raise SyncConfigError([_(
                    'Field "{field_name}" does not exist. Please check your {provider_name} settings.'
                ).format(field_name=key, provider_name=self.display_name)])
        try:
            input = inputs[field.required_input]
        except KeyError:
            with language(self.event.settings.locale):
                raise SyncConfigError([_(
                    'Field "{field_name}" requires {required_input}, but only got {available_inputs}. Please check your {provider_name} settings.'
                ).format(field_name=key, required_input=field.required_input, available_inputs=", ".join(inputs.keys()), provider_name=self.display_name)])
        val = field.getter(input)
        if isinstance(val, list):
            if field.enum_opts and mapping_entry.get("value_map"):
                map = json.loads(mapping_entry["value_map"])
                try:
                    val = [map[el] for el in val]
                except KeyError:
                    with language(self.event.settings.locale):
                        raise SyncConfigError([_(
                            'Please update value mapping for field "{field_name}" - option "{val}" not assigned'
                        ).format(field_name=key, val=val)])

            if self.list_field_joiner:
                val = self.list_field_joiner.join(val)
        return val

    def get_properties(self, inputs: dict, property_mappings: List[dict]):
        return [
            (m["external_field"], self.get_field_value(inputs, m), m["overwrite"])
            for m in property_mappings
        ]

    def sync_object_with_properties(
            self,
            external_id_field: str,
            id_value,
            properties: list,
            inputs: dict,
            mapping: ObjectMapping,
            mapped_objects: dict,
            **kwargs,
    ) -> Optional[dict]:
        """
        This method is called for each object that needs to be created/updated in the external system -- which these are is
        determined by the implementation of the `mapping` property.

        :param external_id_field: Identifier field in the external system as provided in ``mapping.external_identifier``
        :param id_value: Identifier contents as retrieved from the property specified by ``mapping.pretix_identifier`` of the model
                         specified by ``mapping.pretix_model``
        :param properties: All properties defined in ``mapping.property_mappings``, as list of three-tuples
                           ``(external_field, value, overwrite)``
        :param inputs: All pretix model instances from which data can be retrieved for this mapping.
                       Dictionary mapping from sourcefields.ORDER_POSITION, .ORDER, .EVENT, .EVENT_OR_SUBEVENT to the
                       relevant Django model.
                       Most providers don't need to use this parameter directly, as `properties` and `id_value`
                       already contain the values as evaluated from the available inputs.
        :param mapping: The mapping object as returned by ``self.mappings``
        :param mapped_objects: Information about objects that were synced in the same sync run, by mapping definitions
                               *before* the current one in order of ``self.mappings``.
                               Type is a dictionary ``{mapping.id: [list of OrderSyncResult objects]}``
                               Useful to create associations between objects in the target system.

        Example code to create return value::

                 return {
                    # optional:
                    "action": "nothing_to_do",  # to inform that no action was taken, because the data was already up-to-date.
                                                # other values for action (e.g. create, update) currently have no special
                                                # meaning, but are visible for debugging purposes to admins.

                    # optional:
                    "external_link_href": "https://external-system.example.com/backend/link/to/contact/123/",
                    "external_link_display_name": "Contact #123 - Jane Doe",
                    "...optionally further values you need in mapped_objects for association": 123456789,
                 }

        The return value needs to be a JSON serializable dict, or None.

        Return None only in case you decide this object should not be synced at all in this mapping. Do not return None in
        case the object is already up-to-date in the target system (return "action": "nothing_to_do" instead).

        This method needs to be idempotent, i.e. calling it multiple times with the same input values should create
        only a single object in the target system.

        Subsequent calls with the same mapping and id_value should update the existing object, instead of creating a new one.
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
        properties = self.get_properties(inputs, mapping.property_mappings)
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
        if not info:
            return None
        external_link_href = info.pop('external_link_href', None)
        external_link_display_name = info.pop('external_link_display_name', None)
        obj, created = OrderSyncResult.objects.update_or_create(
            order=inputs.get(ORDER), order_position=inputs.get(ORDER_POSITION), sync_provider=self.identifier,
            mapping_id=mapping.id,
            defaults=dict(
                external_object_type=mapping.external_object_type,
                external_id_field=mapping.external_id_field,
                id_value=id_value,
                external_link_href=external_link_href,
                external_link_display_name=external_link_display_name,
                sync_info=info,
                transmitted=now(),
            )
        )
        return obj

    def sync_order(self, order):
        if not self.should_sync_order(order):
            logger.debug("Skipping order %r", order)
            return {}

        logger.debug("Syncing order %r", order)
        positions = list(
            order.all_positions
            .prefetch_related("answers", "answers__question")
            .select_related(
                "voucher",
            )
        )
        order_inputs = {ORDER: order, EVENT: self.event}
        mapped_objects = {}
        for mapping in self.mappings:
            if mapping.pretix_model == 'Order':
                mapped_objects[mapping.id] = [
                    self.sync_object(order_inputs, mapping, mapped_objects)
                ]
            elif mapping.pretix_model == 'OrderPosition':
                mapped_objects[mapping.id] = [
                    self.sync_object({
                        **order_inputs, EVENT_OR_SUBEVENT: op.subevent or self.event, ORDER_POSITION: op
                    }, mapping, mapped_objects)
                    for op in positions
                ]
            else:
                raise SyncConfigError("Invalid pretix model '{}'".format(mapping.pretix_model))
        self.finalize_sync_order(order)
        return mapped_objects

    def filter_mapped_objects(self, mapped_objects, inputs):
        """
        For order positions, only
        """
        if ORDER_POSITION in inputs:
            return {
                mapping_id: [
                    osr for osr in results
                    if osr and (osr.order_position_id is None or osr.order_position_id == inputs[ORDER_POSITION].id)
                ]
                for mapping_id, results in mapped_objects.items()
            }
        else:
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
