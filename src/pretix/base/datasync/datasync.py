import logging
from datetime import datetime, timedelta
from itertools import groupby

import sentry_sdk
from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django_scopes import scopes_disabled, scope

from pretix.base.models import Order, Event
from django.utils.translation import gettext_lazy as _

from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.signals import periodic_task, EventPluginRegistry
from pretix.celery_app import app

logger = logging.getLogger(__name__)


class OrderSyncQueue(models.Model):
    class Meta:
        unique_together = (("order", "sync_target"),)

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="order_sync_jobs"
    )
    sync_target = models.CharField(blank=False, null=False, max_length=128)
    triggered_by = models.CharField(blank=False, null=False, max_length=128)
    triggered = models.DateTimeField(blank=False, null=False, auto_now_add=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    not_before = models.DateTimeField(blank=True, null=True)


@receiver(periodic_task, dispatch_uid="data_sync_periodic")
def on_periodic_task(sender, **kwargs):
    sync_all.apply_async()


sync_targets = EventPluginRegistry({"name": lambda o: o.__name__})


def sync_event_to_target(event, target_cls, queued_orders):
    with scope(organizer=event.organizer):
        with target_cls(event=event) as p:
            p.sync_queued_orders(queued_orders)



@app.task()
def sync_all():
    with scopes_disabled():
        queue = OrderSyncQueue.objects.filter(Q(not_before__isnull=True) | Q(not_before__lt=datetime.now()))[:1000]
        grouped = groupby(sorted(queue, key=lambda q: (q.sync_target, q.order.event)), lambda q: (q.sync_target, q.order.event))
        for (target, event), queued_orders in grouped:
            target_cls = sync_targets.get(name=target)
            sync_event_to_target(event, target_cls, queued_orders)


class SyncConfigError(Exception):
    def __init__(self, messages, full_message=None):
        self.messages = messages
        self.full_message = full_message


class SyncProvider:
    max_attempts = 5

    def __init__(self, event):
        self.event = event

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            self.do_after_event()
        self.do_finally()

    def sync_order(self, order):
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
                    "pretix.order_sync_failed",
                    {
                        "error": e.messages,
                        "full_message": e.full_message,
                    },
                )
                sq.delete()
            except Exception as e:
                sentry_sdk.capture_exception(e)
                sq.failed_attempts += 1
                sq.not_before = self.next_retry_date(sq)
                logger.exception(
                    f"Could not sync order {sq.order.code} to {self.__name__} (transient error, attempt #{sq.failed_attempts})"
                )
                if sq.failed_attempts >= self.max_attempts:
                    sq.order.log_action(
                        "pretix.order_sync_failed",
                        {
                            "error": [_("Marking as failed after {} retries").format(sq.failed_attempts)],
                            "full_message": str(e),
                        },
                    )
                    sq.delete()
                else:
                    sq.save()
            else:
                sq.delete()

