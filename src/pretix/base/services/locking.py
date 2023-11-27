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
from itertools import groupby

from django.conf import settings
from django.db import DatabaseError, connection
from django.utils.timezone import now

from pretix.base.models import Event, Membership, Quota, Seat, Voucher
from pretix.testutils.middleware import debugflags_var

logger = logging.getLogger('pretix.base.locking')

# A lock acquisition is aborted if it takes longer than LOCK_ACQUISITION_TIMEOUT to prevent connection starvation
LOCK_ACQUISITION_TIMEOUT = 3

# We make the assumption that it is safe to e.g. transform an order into a cart if the order has a lifetime of more than
# LOCK_TRUST_WINDOW into the future. In other words, we assume that a lock is never held longer than LOCK_TRUST_WINDOW.
# This assumption holds true for all in-request locks, since our gunicorn default settings kill a worker that takes
# longer than 60 seconds to process a request. It however does not hold true for celery tasks, especially long-running
# ones, so this does introduce *some* risk of incorrect locking.
LOCK_TRUST_WINDOW = 120

# These are different offsets for the different types of keys we want to lock
KEY_SPACES = {
    Event: 1,
    Quota: 2,
    Seat: 3,
    Voucher: 4,
    Membership: 5
}


def pg_lock_key(obj):
    """
    This maps the primary key space of multiple tables to a single bigint key space within postgres. It is not
    an injective function, which is fine, as long as collisions are rare.
    """
    keyspace = KEY_SPACES.get(type(obj))
    objectid = obj.pk
    if not keyspace:
        raise ValueError(f"No key space defined for locking objects of type {type(obj)}")
    assert isinstance(objectid, int)
    # 64bit int: xxxxxxxx xxxxxxx xxxxxxx xxxxxxx xxxxxx xxxxxxx xxxxxxx xxxxxxx
    #            |              objectid mod 2**48             | |index| |keysp.|
    key = ((objectid % 281474976710656) << 16) | ((settings.DATABASE_ADVISORY_LOCK_INDEX % 256) << 8) | (keyspace % 256)
    return key


class LockTimeoutException(Exception):
    pass


def lock_objects(objects, *, shared_lock_objects=None, replace_exclusive_with_shared_when_exclusive_are_more_than=20):
    """
    Create an exclusive lock on the objects passed in `objects`. This function MUST be called within an atomic
    transaction and SHOULD be called only once per transaction to prevent deadlocks.

    A shared lock will be created on objects passed in `shared_lock_objects`.

    If `objects` contains more than `replace_exclusive_with_shared_when_exclusive_are_more_than` objects, `objects`
    will be ignored and `shared_lock_objects` will be used in its place and receive an exclusive lock.

    The idea behind it is this: Usually we create a lock on every quota, voucher, or seat contained in an order.
    However, this has a large performance penalty in case we have hundreds of locks required. Therefore, we always
    place a shared lock in the event, and if we have too many affected objects, we fall back to event-level locks.
    """
    if (not objects and not shared_lock_objects) or 'skip-locking' in debugflags_var.get():
        return

    if 'fail-locking' in debugflags_var.get():
        raise LockTimeoutException()

    if not connection.in_atomic_block:
        raise RuntimeError(
            "You cannot create locks outside of an transaction"
        )

    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
        shared_keys = set(pg_lock_key(obj) for obj in shared_lock_objects) if shared_lock_objects else set()
        exclusive_keys = set(pg_lock_key(obj) for obj in objects)
        if replace_exclusive_with_shared_when_exclusive_are_more_than and shared_keys and \
                len(exclusive_keys) > replace_exclusive_with_shared_when_exclusive_are_more_than:
            exclusive_keys = shared_keys
        keys = sorted(list(shared_keys | exclusive_keys))
        calls = ", ".join([
            (f"pg_advisory_xact_lock({k})" if k in exclusive_keys else f"pg_advisory_xact_lock_shared({k})") for k in keys
        ])

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_ACQUISITION_TIMEOUT}s';")
                cursor.execute(f"SELECT {calls};")
                cursor.execute("SET LOCAL lock_timeout = '0';")  # back to default
        except DatabaseError as e:
            logger.warning(f"Waiting for locks timed out: {e} on SELECT {calls};")
            raise LockTimeoutException()

    else:
        for model, instances in groupby(objects, key=lambda o: type(o)):
            model.objects.select_for_update().filter(pk__in=[o.pk for o in instances])


class NoLockManager:
    def __init__(self):
        pass

    def __enter__(self):
        return now()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
