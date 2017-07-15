from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.dummy import DummyCache


class CustomDummyCache(DummyCache):
    def get_or_set(self, key, default, timeout=DEFAULT_TIMEOUT, version=None):
        if callable(default):
            default = default()
        return default
