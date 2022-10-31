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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from pretix.base.models import EventLock

logger = logging.getLogger('pretix.base.locking')
LOCK_TIMEOUT = 120


class NoLockManager:
    def __init__(self):
        pass

    def __enter__(self):
        return now()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False


class LockManager:
    def __init__(self, event):
        self.event = event

    def __enter__(self):
        lock_event(self.event)
        return now()

    def __exit__(self, exc_type, exc_val, exc_tb):
        release_event(self.event)
        if exc_type is not None:
            return False


class LockTimeoutException(Exception):
    pass


class LockReleaseException(LockTimeoutException):
    pass


def lock_event(event):
    """
    Issue a lock on this event so nobody can book tickets for this event until
    you release the lock. Will retry 5 times on failure.

    :raises LockTimeoutException: if the event is locked every time we try
                                  to obtain the lock
    """
    if hasattr(event, '_lock') and event._lock:
        return True

    if settings.HAS_REDIS:
        return lock_event_redis(event)
    else:
        return lock_event_db(event)


def release_event(event):
    """
    Release a lock placed by :py:meth:`lock()`. If the parameter force is not set to ``True``,
    the lock will only be released if it was issued in _this_ python
    representation of the database object.

    :raises LockReleaseException: if we do not own the lock
    """
    if not hasattr(event, '_lock') or not event._lock:
        raise LockReleaseException('Lock is not owned by this thread')
    if settings.HAS_REDIS:
        return release_event_redis(event)
    else:
        return release_event_db(event)


def lock_event_db(event):
    retries = 5
    for i in range(retries):
        with transaction.atomic():
            dt = now()
            l, created = EventLock.objects.get_or_create(event=event.id)
            if created:
                event._lock = l
                return True
            elif l.date < now() - timedelta(seconds=LOCK_TIMEOUT):
                newtoken = str(uuid.uuid4())
                updated = EventLock.objects.filter(event=event.id, token=l.token).update(date=dt, token=newtoken)
                if updated:
                    l.token = newtoken
                    event._lock = l
                    return True
        time.sleep(2 ** i / 100)
    raise LockTimeoutException()


@transaction.atomic
def release_event_db(event):
    if not hasattr(event, '_lock') or not event._lock:
        raise LockReleaseException('Lock is not owned by this thread')
    try:
        lock = EventLock.objects.get(event=event.id, token=event._lock.token)
        lock.delete()
        event._lock = None
    except EventLock.DoesNotExist:
        raise LockReleaseException('Lock is no longer owned by this thread')


def redis_lock_from_event(event):
    from django_redis import get_redis_connection
    from redis.lock import Lock

    if not hasattr(event, '_lock') or not event._lock:
        rc = get_redis_connection("redis")
        event._lock = Lock(redis=rc, name='pretix_event_%s' % event.id, timeout=LOCK_TIMEOUT)
    return event._lock


def lock_event_redis(event):
    from redis.exceptions import RedisError

    lock = redis_lock_from_event(event)
    retries = 5
    for i in range(retries):
        try:
            if lock.acquire(blocking=False):
                return True
        except RedisError:
            logger.exception('Error locking an event')
            raise LockTimeoutException()
        time.sleep(2 ** i / 100)
    raise LockTimeoutException()


def release_event_redis(event):
    from redis import RedisError

    lock = redis_lock_from_event(event)
    try:
        lock.release()
    except RedisError:
        logger.exception('Error releasing an event lock')
        raise LockReleaseException()
    event._lock = None
