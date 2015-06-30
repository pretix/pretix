from datetime import timedelta
import logging
import time
from django.db.models import Q
from django.utils.timezone import now
from pretix import settings

from pretix.base.models import Quota
from redis import RedisError

logger = logging.getLogger('pretix.base.locking')


def lock_quota(quota):
    """
    Issue a lock on this quota so nobody can take tickets from this quota until
    you release the lock. Will retry 5 times on failure.

    :raises Quota.LockTimeoutException: if the quota is locked every time we try
                                        to obtain the lock
    """
    if settings.HAS_REDIS:
        return lock_quota_redis(quota)
    else:
        return lock_quota_db(quota)


def lock_quota_db(quota):
    retries = 5
    for i in range(retries):
        dt = now()

        updated = Quota.objects.current.filter(
            Q(identity=quota.identity)
            & Q(Q(locked__lt=dt - timedelta(seconds=120)) | Q(locked__isnull=True))
            & Q(version_end_date__isnull=True)
        ).update(
            locked=dt
        )
        if updated:
            quota.locked_here = dt
            quota.locked = dt
            return True
        time.sleep(2 ** i / 100)
    raise Quota.LockTimeoutException()


def release_quota(quota, force=False):
    """
    Release a lock placed by :py:meth:`lock()`. If the parameter force is not set to ``True``,
    the lock will only be released if it was issued in _this_ python
    representation of the database object.
    """
    if not quota.locked_here and not force:
        return False
    if settings.HAS_REDIS:
        return release_quota_redis(quota)
    else:
        return release_quota_db(quota)


def release_quota_db(quota):
    updated = Quota.objects.current.filter(
        identity=quota.identity,
        version_end_date__isnull=True
    ).update(
        locked=None
    )
    quota.locked_here = None
    quota.locked = None
    return updated


def redis_lock_from_quota(quota):
    from django_redis import get_redis_connection
    from redis.lock import Lock

    if not hasattr(quota, '_redis_lock'):
        rc = get_redis_connection("redis")
        quota._redis_lock = Lock(redis=rc, name='pretix_quota_%s' % quota.identity, timeout=120)
    return quota._redis_lock


def lock_quota_redis(quota):
    from redis.exceptions import RedisError
    lock = redis_lock_from_quota(quota)
    retries = 5
    for i in range(retries):
        dt = now()
        try:
            if lock.acquire(False):
                quota.locked_here = dt
                quota.locked = dt
                return True
        except RedisError:
            logger.exception('Error locking a quota')
            raise Quota.LockTimeoutException()
        time.sleep(2 ** i / 100)
    raise Quota.LockTimeoutException()


def release_quota_redis(quota):
    lock = redis_lock_from_quota(quota)
    try:
        lock.release()
    except RedisError:
        logger.exception('Error releasing a quota lock')
        raise Quota.LockTimeoutException()
    quota.locked_here = None
    quota.locked = None
    return True
