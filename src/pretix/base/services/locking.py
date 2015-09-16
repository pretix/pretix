import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from pretix.base.models import EventLock

logger = logging.getLogger('pretix.base.locking')


class LockManager:
    def __init__(self, event):
        self.event = event

    def __enter__(self):
        lock_event(self.event)

    def __exit__(self, exc_type, exc_val, exc_tb):
        release_event(self.event)
        if exc_type is not None:
            return False


def lock_event(event):
    """
    Issue a lock on this event so nobody can book tickets for this event until
    you release the lock. Will retry 5 times on failure.

    :raises EventLock.LockTimeoutException: if the event is locked every time we try
                                            to obtain the lock
    """
    if event.locked_here:
        return True
    if settings.HAS_REDIS:
        return lock_event_redis(event)
    else:
        return lock_event_db(event)


def release_event(event, force=False):
    """
    Release a lock placed by :py:meth:`lock()`. If the parameter force is not set to ``True``,
    the lock will only be released if it was issued in _this_ python
    representation of the database object.
    """
    if not event.locked_here and not force:
        return False
    if settings.HAS_REDIS:
        return release_event_redis(event)
    else:
        return release_event_db(event)


def lock_event_db(event):
    retries = 5
    for i in range(retries):
        with transaction.atomic():
            dt = now()
            l, created = EventLock.objects.get_or_create(event=event.identity)
            if created:
                event.locked_here = dt
                return True
            elif l.date < now() - timedelta(seconds=120):
                updated = EventLock.objects.filter(event=event.identity, date=l.date).update(date=dt)
                if updated:
                    event.locked_here = dt
                    return True
        time.sleep(2 ** i / 100)
    raise EventLock.LockTimeoutException()


def release_event_db(event):
    deleted = EventLock.objects.filter(event=event.identity).delete()
    event.locked_here = None
    return deleted


def redis_lock_from_event(event):
    from django_redis import get_redis_connection
    from redis.lock import Lock

    if not hasattr(event, '_redis_lock'):
        rc = get_redis_connection("redis")
        event._redis_lock = Lock(redis=rc, name='pretix_event_%s' % event.identity, timeout=120)
    return event._redis_lock


def lock_event_redis(event):
    from redis.exceptions import RedisError

    lock = redis_lock_from_event(event)
    retries = 5
    for i in range(retries):
        dt = now()
        try:
            if lock.acquire(False):
                event.locked_here = dt
                return True
        except RedisError:
            logger.exception('Error locking an event')
            raise EventLock.LockTimeoutException()
        time.sleep(2 ** i / 100)
    raise EventLock.LockTimeoutException()


def release_event_redis(event):
    from redis import RedisError

    lock = redis_lock_from_event(event)
    try:
        lock.release()
    except RedisError:
        logger.exception('Error releasing an event lock')
        raise EventLock.LockTimeoutException()
    event.locked_here = None
    return True
