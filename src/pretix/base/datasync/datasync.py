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
from pretix.base.models import Event, Order
from pretix.base.services.tasks import TransactionAwareTask
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
        grouped = groupby(sorted(queue, key=lambda q: (q.sync_target, q.order.event)), lambda q: (q.sync_target, q.order.event))
        for (target, event), queued_orders in grouped:
            target_cls = sync_targets.get(identifier=target)
            sync_event_to_target(event, target_cls, queued_orders)


class SyncConfigError(Exception):
    def __init__(self, messages, full_message=None):
        self.messages = messages
        self.full_message = full_message


StaticMapping = namedtuple('StaticMapping', ('pk', 'pretix_model', 'external_object_type', 'pretix_pk', 'external_pk', 'property_mapping'))


class OutboundSyncProvider:
    #identifier = None
    max_attempts = 5
    syncer_class = None

    def __init__(self, event):
        self.event = event

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            self.do_after_event()
        self.do_finally()

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

    def do_after_event(self):
        pass

    def do_finally(self):
        pass

    def next_retry_date(self, sq):
        return datetime.now() + timedelta(days=1)

    def sync_queued_orders(self, queued_orders):
        for sq in queued_orders:
            try:
                self.sync_order(sq.order)
            except SyncConfigError as e:
                logger.warning(
                    f"Could not sync order {sq.order.code} to {self.__name__} (config error)",
                    exc_info=True,
                )
                sq.order.log_action(
                    "pretix.event.order.data_sync.failed",
                    {
                        "error": e.messages,
                        "full_message": e.full_message,
                    },
                )
                sq.delete()
            except Exception as e:
                # TODO: different handling per Exception, or even per HTTP response code?
                #       otherwise, SyncProviders should always throw SyncConfigError in non-recoverable situations
                sq.failed_attempts += 1
                sq.not_before = self.next_retry_date(sq)
                logger.exception(
                    f"Could not sync order {sq.order.code} to {self.__name__} (transient error, attempt #{sq.failed_attempts})"
                )
                if sq.failed_attempts >= self.max_attempts:
                    sentry_sdk.capture_exception(e)
                    sq.order.log_action(
                        "pretix.event.order.data_sync.failed",
                        {
                            "error": [_("Maximum number of retries exceeded.")],
                            "full_message": str(e),
                        },
                    )
                    sq.delete()
                else:
                    sq.save()
            else:
                sq.delete()

    def order_valid_for_sync(self, order):
        return True

    @property
    def mappings(self):
        raise NotImplemented

    @cached_property
    def data_fields(self):
        return {
            key: (from_model, label, ptype, enum_opts, getter)
            for (from_model, key, label, ptype, enum_opts, getter) in get_data_fields(self.event)
        }

    def get_field_value(self, inputs, mapping_entry):
        key = mapping_entry["pretix_field"]
        required_input, label, ptype, enum_opts, getter = self.data_fields.get(key)
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

        return self.sync_object_with_properties(inputs, mapping, mapped_objects, pk_value, properties)

    def sync_order(self, order):
        if not self.order_valid_for_sync(order):
            logger.debug("Skipping order (not valid for sync)", order)
            return

        logger.debug("Syncing order", order)
        positions = list(
            order.all_positions.filter(item__admission=True)
            .prefetch_related("answers", "answers__question")
            .select_related(
                "voucher",
            )
        )
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
        order.log_action(
            "pretix.event.order.data_sync.success", {"objects": mapped_objects}
        )


