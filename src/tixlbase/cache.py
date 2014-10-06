import time
import hashlib

from django.core.cache import caches


class EventRelatedCache:
    """
    This object behaves exactly like the cache implementations by Django
    but with one important difference: It stores all keys related to a
    certain event, so you pass an event when creating this object and if
    you store data in this cache, it is only stored for this event. The
    main purpose of this is to be able to flush all cached data related
    to this event at once.
    """

    def __init__(self, event, cache='default'):
        self.cache = caches[cache]
        self.prefix = self._build_prefix()
        self.prefixkey = 'event:%d' % self.event.pk

    def _prefix_key(self, original_key):
        # Race conditions can happen here, but should be very very rare.
        # We could only handle this by going _really_ lowlevel using
        # memcached's `add` keyword instead of `set`.
        # See also:
        # https://code.google.com/p/memcached/wiki/NewProgrammingTricks#Namespacing
        prefix = self.cache.get(self.prefixkey)
        if prefix is None:
            prefix = int(time.time())
            self.cache.set(self.prefixkey, prefix)
        key = 'event:%d:%d:%s' % (self.event.pk, prefix, original_key)
        if len(key) > 200:  # Hash long keys, as memcached has a length limit
            # TODO: Use a more efficient, non-cryptographic hash algorithm
            key = hashlib.sha256(key.encode("UTF-8")).hexdigest()
        return key

    def clear(self):
        try:
            prefix = self.cache.incr(self.prefixkey, 1)
        except ValueError:
            prefix = int(time.time())
            self.cache.set(self.prefixkey, prefix)

    def set(self, key, value, timeout=300):
        return self.cache.set(self._prefix_key(key), value, timeout)

    def get(self, key):
        return self.cache.get(self._prefix_key(key))

    def get_many(self, keys):
        return self.cache.get_many([self._prefix_key(key) for key in keys])

    def set_many(self, values, timeout=300):
        newvalues = {}
        for i in values.items():
            newvalues[self._prefix_key(i[0])] = i[1]
        return self.cache.set_many([newvalues], timeout)

    def delete(self, key):
        return self.cache.delete(self._prefix_key(key))

    def delete_many(self, keys):
        return self.cache.delete_many([self._prefix_key(key) for key in keys])

    def incr(self, key, by=1):
        return self.cache.incr(self._prefix_key(key), by)

    def decr(self, key, by=1):
        return self.cache.decr(self._prefix_key(key), by)

    def close(self):
        pass
