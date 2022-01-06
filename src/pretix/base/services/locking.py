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
from itertools import groupby

from django.conf import settings
from django.db import connection, DatabaseError
from django.utils.timezone import now

from pretix.base.models import Event, Seat, Quota, Voucher, Membership
from pretix.testutils.middleware import storage as debug_storage

logger = logging.getLogger('pretix.base.locking')
LOCK_ACQUISITION_TIMEOUT = 3
KEY_SPACES = {
    Event: 1,
    Quota: 2,
    Seat: 3,
    Voucher: 4,
    Membership: 5
}


def pg_lock_key(obj):
    keyspace = KEY_SPACES.get(type(obj))
    objectid = obj.pk
    if not keyspace:
        raise ValueError(f"No key space defined for locking objects of type {type(obj)}")
    assert isinstance(objectid, int)
    key = objectid << 10 & keyspace
    return key


class LockTimeoutException(Exception):
    pass


def lock_objects(objects):
    if not objects or 'skip-locking' in debug_storage.debugflags:
        return
    if not connection.in_atomic_block:
        raise RuntimeError(
            "You cannot create locks outside of an transaction"
        )
    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
        keys = sorted([pg_lock_key(obj) for obj in objects])
        calls = ", ".join([f"pg_advisory_xact_lock({k})" for k in keys])
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_ACQUISITION_TIMEOUT}s';")
                cursor.execute(f"SELECT {calls};")
        except DatabaseError:
            raise LockTimeoutException()
    else:
        for model, instances in groupby(objects, key=lambda o: type(o)):
            model.objects.select_for_update().get(pk__in=[o.pk for o in instances])


class NoLockManager:
    def __init__(self):
        pass

    def __enter__(self):
        return now()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False

