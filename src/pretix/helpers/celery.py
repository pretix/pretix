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
from typing import Union

from celery import Task
from celery.result import AsyncResult
from django.conf import settings
from django.core.exceptions import SuspiciousOperation

THRESHOLD_DOWNGRADE_TO_MID = 50
THRESHOLD_DOWNGRADE_TO_LOW = 250


def get_task_priority(shard, organizer_id):
    """
    This is an attempt to build a simple "fair-use" policy for webhooks and notifications. The problem is that when
    one organizer creates e.g. 20,000 orders through the API, that might schedule 20,000 webhooks and every other
    organizer will need to wait for these webhooks to go through.

    We try to fix that by building three queues: high-prio, mid-prio, and low-prio. Every organizer starts in the
    high-prio queue, and all their tasks are routed immediately. Once an organizer submits more than X jobs of a
    certain type per minute, they get downgraded to the mid-prio queue, and then – if they submit even more – to the
    low-prio queue. That way, if another organizer has "regular usage", they are prioritized over the organizer with
    high load.
    """
    from django_redis import get_redis_connection

    if not settings.HAS_REDIS:
        return settings.PRIORITY_CELERY_HIGH

    # We use redis directly instead of the Django cache API since the Django cache API does not support INCR for
    # nonexistant keys
    rc = get_redis_connection("redis")

    cache_key = f"pretix:task_priority:{shard}:{organizer_id}"

    # Make sure counters expire after a while when not used
    p = rc.pipeline()
    p.incr(cache_key)
    p.expire(cache_key, 60)
    new_counter = p.execute()[0]

    if new_counter >= THRESHOLD_DOWNGRADE_TO_LOW:
        return settings.PRIORITY_CELERY_LOW
    elif new_counter >= THRESHOLD_DOWNGRADE_TO_MID:
        return settings.PRIORITY_CELERY_MID
    else:
        return settings.PRIORITY_CELERY_HIGH


class SafeAsyncResult(AsyncResult):
    def __init__(self, *args, expected_task_name, **kwargs):
        super().__init__(*args, **kwargs)
        self.__expected_task_name = expected_task_name

    def _maybe_set_cache(self, meta):
        if meta and meta['status'] != "PENDING":
            if meta.get('name') != self.__expected_task_name:
                raise SuspiciousOperation(
                    f"Received task result for {meta.get('name')!r}, but expected '{self.__expected_task_name}'"
                )
        return super()._maybe_set_cache(meta)


def get_task_result(task_id: str, task_name: Union[Task, str]) -> SafeAsyncResult:
    """
    Returns an AsyncResult by it's ID in a safe way, i.e. do not return anything if the task
    name does not match the expected task.
    """
    if isinstance(task_name, Task):
        task_name = task_name.name
    return SafeAsyncResult(task_id, expected_task_name=task_name)
