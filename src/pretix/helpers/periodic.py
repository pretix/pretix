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
import logging
import uuid
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)

SKIPPED = object()


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
                return SKIPPED

            result_val = cache.get(key_result)
            if result_val:
                # Has run recently
                return SKIPPED

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
