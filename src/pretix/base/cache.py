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
import hashlib
import time
from typing import Callable, Dict, List

from django.core.cache import caches
from django.db.models import Model


class NamespacedCache:

    def __init__(self, prefixkey: str, cache: str='default'):
        self.cache = caches[cache]
        self.prefixkey = prefixkey
        self._last_prefix = None

    def _prefix_key(self, original_key: str, known_prefix=None) -> str:
        # Race conditions can happen here, but should be very very rare.
        # We could only handle this by going _really_ lowlevel using
        # memcached's `add` keyword instead of `set`.
        # See also:
        # https://code.google.com/p/memcached/wiki/NewProgrammingTricks#Namespacing
        prefix = known_prefix or self.cache.get(self.prefixkey)
        if prefix is None:
            prefix = int(time.time())
            self.cache.set(self.prefixkey, prefix)
        self._last_prefix = prefix
        key = '%s:%d:%s' % (self.prefixkey, prefix, original_key)
        if len(key) > 200:  # Hash long keys, as memcached has a length limit
            # TODO: Use a more efficient, non-cryptographic hash algorithm
            key = hashlib.sha256(key.encode("UTF-8")).hexdigest()
        return key

    def _strip_prefix(self, key: str) -> str:
        return key.split(":", 2 + self.prefixkey.count(":"))[-1]

    def clear(self) -> None:
        self._last_prefix = None
        try:
            prefix = self.cache.incr(self.prefixkey, 1)
        except ValueError:
            prefix = int(time.time())
            self.cache.set(self.prefixkey, prefix)

    def set(self, key: str, value: str, timeout: int=300):
        return self.cache.set(self._prefix_key(key), value, timeout)

    def get(self, key: str) -> str:
        return self.cache.get(self._prefix_key(key, known_prefix=self._last_prefix))

    def get_or_set(self, key: str, default: Callable, timeout=300) -> str:
        return self.cache.get_or_set(
            self._prefix_key(key, known_prefix=self._last_prefix),
            default=default,
            timeout=timeout
        )

    def get_many(self, keys: List[str]) -> Dict[str, str]:
        values = self.cache.get_many([self._prefix_key(key) for key in keys])
        newvalues = {}
        for k, v in values.items():
            newvalues[self._strip_prefix(k)] = v
        return newvalues

    def set_many(self, values: Dict[str, str], timeout=300):
        newvalues = {}
        for k, v in values.items():
            newvalues[self._prefix_key(k)] = v
        return self.cache.set_many(newvalues, timeout)

    def delete(self, key: str):  # NOQA
        return self.cache.delete(self._prefix_key(key))

    def delete_many(self, keys: List[str]):  # NOQA
        return self.cache.delete_many([self._prefix_key(key) for key in keys])

    def incr(self, key: str, by: int=1):  # NOQA
        return self.cache.incr(self._prefix_key(key), by)

    def decr(self, key: str, by: int=1):  # NOQA
        return self.cache.decr(self._prefix_key(key), by)

    def close(self):  # NOQA
        pass


class ObjectRelatedCache(NamespacedCache):
    """
    This object behaves exactly like the cache implementations by Django
    but with one important difference: It stores all keys related to a
    certain object, so you pass an object when creating this object and if
    you store data in this cache, it is only stored for this object. The
    main purpose of this is to be able to flush all cached data related
    to this object at once.

    The ObjectRelatedCache instance itself is stateless, all state is
    stored in the cache backend, so you can instantiate this class as many
    times as you want.
    """

    def __init__(self, obj: Model, cache: str='default'):
        assert isinstance(obj, Model)
        super().__init__('%s:%s' % (obj._meta.object_name, obj.pk), cache)
