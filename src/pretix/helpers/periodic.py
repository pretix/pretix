import logging
import uuid
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)


def minimum_interval(minutes_after_success, minutes_after_error=0, minutes_running_timeout=30):
    """
    This is intended to be used as a decorator on receivers of the ``periodic_task`` signal.
    It stores the result in the task in the cache (usually redis) to ensure the receiver function
    isn't executed less than ``minutes_after_success`` after the last successful run and no less
    than ``minutes_after_error`` after the last failed run. There's also a simple locking mechanism
    implemented making sure the function is not called a second time while it is running, unless
    ``minutes_running_timeout`` have passed. This locking mechanism is naive and not safe of
    race-conditions, it should not be relied upon.
    """
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key_running = f'pretix_periodic_{f.__module__}.{f.__name__}_running'
            key_result = f'pretix_periodic_{f.__module__}.{f.__name__}_result'

            running_val = cache.get(key_running)
            if running_val:
                # Currently running
                return

            result_val = cache.get(key_result)
            if result_val:
                # Has run recently
                return

            uniqid = str(uuid.uuid4())
            cache.set(key_running, uniqid, timeout=minutes_running_timeout * 60)
            try:
                retval = f(*args, **kwargs)
            except Exception as e:
                try:
                    cache.set(key_result, 'error', timeout=minutes_after_error * 60)
                except:
                    logger.exception('Could not store result')
                raise e
            else:
                try:
                    cache.set(key_result, 'success', timeout=minutes_after_success * 60)
                except:
                    logger.exception('Could not store result')
                return retval
            finally:
                try:
                    if cache.get(key_running) == uniqid:
                        cache.delete(key_running)
                except:
                    logger.exception('Could not release lock')

        return wrapper

    return deco
