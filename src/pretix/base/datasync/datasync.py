import json
import logging
from collections import namedtuple
from datetime import datetime, timedelta
from functools import cached_property
from itertools import groupby

import sentry_sdk
from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled

from pretix.base.datasync.sourcefields import (
    EVENT, EVENT_OR_SUBEVENT, ORDER, ORDER_POSITION, get_data_fields,
)
from pretix.base.logentrytype_registry import make_link
from pretix.base.models import Order, OrderPosition
from pretix.base.signals import EventPluginRegistry, periodic_task
from pretix.celery_app import app

logger = logging.getLogger(__name__)

MODE_OVERWRITE = "overwrite"
MODE_SET_IF_NEW = "if_new"
MODE_SET_IF_EMPTY = "if_empty"
MODE_APPEND_LIST = "append"


class OrderSyncQueue(models.Model):
    class Meta:
        unique_together = (("order", "sync_provider"),)

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="queued_sync_jobs"
    )
    sync_provider = models.CharField(blank=False, null=False, max_length=128)
    triggered_by = models.CharField(blank=False, null=False, max_length=128)
    triggered = models.DateTimeField(blank=False, null=False, auto_now_add=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    not_before = models.DateTimeField(blank=True, null=True)

    @cached_property
    def _provider_class_info(self):
        return sync_targets.get(identifier=self.sync_provider)

    @property
    def provider_class(self):
        return self._provider_class_info[0]

    @property
    def is_provider_active(self):
        return self._provider_class_info[1]

    @property
    def max_retry_attempts(self):
        return self.provider_class.max_attempts


class OrderSyncLink(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=("order", "sync_provider")),
        ]
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="synced_objects"
    )
    sync_provider = models.CharField(blank=False, null=False, max_length=128)
    order_position = models.ForeignKey(
        OrderPosition, on_delete=models.CASCADE, related_name="synced_objects", blank=True, null=True,
    )
    external_object_type = models.CharField(blank=False, null=False, max_length=128)
    external_pk_name = models.CharField(blank=False, null=False, max_length=128)
    external_pk_value = models.CharField(blank=False, null=False, max_length=128)
    external_link_href = models.CharField(blank=True, null=True, max_length=255)
    external_link_display_name = models.CharField(blank=True, null=True, max_length=255)
    timestamp = models.DateTimeField(blank=False, null=False, auto_now_add=True)

    def external_link_html(self):
        if not self.external_link_display_name:
            return None

        prov, meta = sync_targets.get(identifier=self.sync_provider)
        if prov:
            return prov.get_external_link_html(self.order.event, self.external_link_href, self.external_link_display_name)


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
            .filter(Q(not_before__isnull=True) | Q(not_before__lt=datetime.now()))[:1000]
        )
        grouped = groupby(sorted(queue, key=lambda q: (q.sync_provider, q.order.event)), lambda q: (q.sync_provider, q.order.event))
        for (target, event), queued_orders in grouped:
            target_cls, meta = sync_targets.get(identifier=target, active_in=event)
            # TODO: what should i do if the sync plugin got deactivated in the meantime?
            sync_event_to_target(event, target_cls, queued_orders)


class SyncConfigError(Exception):
    def __init__(self, messages, full_message=None):
        self.messages = messages
        self.full_message = full_message


StaticMapping = namedtuple('StaticMapping', ('pk', 'pretix_model', 'external_object_type', 'pretix_pk', 'external_pk', 'property_mapping'))


class OutboundSyncProvider:
    max_attempts = 5
    syncer_class = None

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
        OrderSyncQueue.objects.create(
            order=order,
            sync_provider=cls.identifier,
            triggered_by=triggered_by,
            not_before=not_before)

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
        return datetime.now() + timedelta(hours=1)

    def sync_queued_orders(self, queued_orders):
        for sq in queued_orders:
            try:
                mapped_objects = self.sync_order(sq.order)
            except SyncConfigError as e:
                logger.warning(
                    f"Could not sync order {sq.order.code} to {type(self).__name__} (config error)",
                    exc_info=True,
                )
                sq.order.log_action("pretix.event.order.data_sync.failed", {
                    "provider": self.identifier,
                    "error": e.messages,
                    "full_message": e.full_message,
                })
                sq.delete()
            except Exception as e:
                # TODO: different handling per Exception, or even per HTTP response code?
                #       otherwise, SyncProviders should always throw SyncConfigError in non-recoverable situations
                sq.failed_attempts += 1
                sq.not_before = self.next_retry_date(sq)
                logger.exception(
                    f"Could not sync order {sq.order.code} to {type(self).__name__} (transient error, attempt #{sq.failed_attempts})"
                )
                if sq.failed_attempts >= self.max_attempts:
                    sentry_sdk.capture_exception(e)
                    sq.order.log_action("pretix.event.order.data_sync.failed", {
                        "provider": self.identifier,
                        "error": [_("Maximum number of retries exceeded.")],
                        "full_message": str(e),
                    })
                    sq.delete()
                else:
                    sq.save()
            else:
                sq.order.log_action("pretix.event.order.data_sync.success", {
                    "provider": self.identifier,
                    "objects": mapped_objects
                })
                sq.delete()

    def order_valid_for_sync(self, order):
        return True

    @property
    def mappings(self):
        raise NotImplementedError

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

    def sync_object(
            self,
            inputs: dict,
            mapping,
            mapped_objects: dict,
    ):
        logger.debug("Syncing object %r, %r, %r", inputs, mapping, mapped_objects)
        properties = self.get_properties(inputs, mapping.property_mapping)
        logger.debug("Properties: %r", properties)

        pk_value = self.get_field_value(inputs, {"pretix_field": mapping.pretix_pk})
        if not pk_value:
            return None

        info = self.sync_object_with_properties(inputs, mapping, mapped_objects, pk_value, properties)
        OrderSyncLink.objects.create(
            order=inputs.get(ORDER), order_position=inputs.get(ORDER_POSITION), sync_provider=self.identifier,
            external_object_type=info.get('object_type'),
            external_pk_name=info.get('pk_field'),
            external_pk_value=info.get('pk_value'),
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
            order.all_positions.filter(item__admission=True)
            .prefetch_related("answers", "answers__question")
            .select_related(
                "voucher",
            )
        )
        order.synced_objects.filter(sync_provider=self.identifier).delete()
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

    """
    Called after sync_object has been called successfully for all objects of a specific order. Can be used for saving
    bulk information per order.
    """
    def finalize_sync_order(self, order):
        pass

    """
    Called after all orders of an event have been synced. Can be used for clean-up tasks (closing a session etc).
    """
    def close(self):
        pass
