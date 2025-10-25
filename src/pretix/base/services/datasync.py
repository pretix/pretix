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

import logging
from datetime import timedelta
from itertools import groupby

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.datasync.datasync import datasync_providers
from pretix.base.models.datasync import OrderSyncQueue
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.signals import periodic_task
from pretix.celery_app import app

logger = logging.getLogger(__name__)


@receiver(periodic_task, dispatch_uid="data_sync_periodic_sync_all")
def periodic_sync_all(sender, **kwargs):
    sync_all.apply_async()


@receiver(periodic_task, dispatch_uid="data_sync_periodic_reset_in_flight")
def periodic_reset_in_flight(sender, **kwargs):
    for sq in OrderSyncQueue.objects.filter(
        in_flight=True,
        in_flight_since__lt=now() - timedelta(minutes=20),
    ):
        sq.set_sync_error('timeout', [], 'Timeout')


def run_sync(queue):
    grouped = groupby(sorted(queue, key=lambda q: (q.sync_provider, q.event.pk)), lambda q: (q.sync_provider, q.event))
    for (target, event), queued_orders in grouped:
        target_cls, meta = datasync_providers.get(identifier=target, active_in=event)

        if not target_cls:
            # sync plugin not found (plugin deactivated or uninstalled) -> drop outstanding jobs
            num_deleted, _ = OrderSyncQueue.objects.filter(pk__in=[sq.pk for sq in queued_orders]).delete()
            logger.info("Deleted %d queue entries from %r because plugin %s inactive", num_deleted, event, target)
            continue

        with scope(organizer=event.organizer):
            with target_cls(event=event) as p:
                p.sync_queued_orders(queued_orders)


@app.task()
def sync_all():
    with scopes_disabled():
        queue = (
            OrderSyncQueue.objects
            .filter(
                in_flight=False,
                not_before__lt=now(),
                need_manual_retry__isnull=True,
            )
            .order_by(Window(
                expression=RowNumber(),
                partition_by=[F("event_id")],
                order_by="not_before",
            ))
            .prefetch_related("event")
            [:1000]
        )
        run_sync(queue)


@app.task(base=TransactionAwareTask)
def sync_single(queue_item_id: int):
    with scopes_disabled():
        queue = (
            OrderSyncQueue.objects
            .filter(
                pk=queue_item_id,
                in_flight=False,
                not_before__lt=now(),
                need_manual_retry__isnull=True,
            )
            .prefetch_related("event")
        )
        run_sync(queue)
