from django.core.cache import cache
from django.utils.translation import get_language
from django_countries import Countries
from django_countries.fields import CountryField


class CachedCountries(Countries):
    _cached_lists = {}
    cache_subkey = None

    def __iter__(self):
        """
        Iterate through countries, sorted by name, but cache the results based on the locale.
        django-countries performs a unicode-aware sorting based on pyuca which is incredibly
        slow.
        """
        cache_key = "countries:all:{}".format(get_language())
        if self.cache_subkey:
            cache_key += ":" + self.cache_subkey
        if cache_key in self._cached_lists:
            yield from self._cached_lists[cache_key]
            return

        val = cache.get(cache_key)
        if val:
            self._cached_lists[cache_key] = val
            yield from val
            return

        val = list(super().__iter__())
        self._cached_lists[cache_key] = val
        cache.set(cache_key, val, 3600 * 24 * 30)
        yield from val


class FastCountryField(CountryField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("countries", CachedCountries)

        if "max_length" not in kwargs:
            # Override logic from CountryField to include 20% buffer. We don't want to migrate our database
            # every time a new country is added to the system!
            if kwargs.get("multiple", False):
                kwargs["max_length"] = int(len(kwargs['countries']()) * 3 * 1.2)
            else:
                kwargs["max_length"] = 2

        super().__init__(*args, **kwargs)

    def check(self, **kwargs):
        # Disable _check_choices since it would require sorting all country names at every import of this field,
        # which takes 1-2 seconds
        return [
            *self._check_field_name(),
            # *self._check_choices(),
            *self._check_db_index(),
            *self._check_null_allowed_for_primary_keys(),
            *self._check_backend_specific_checks(**kwargs),
            *self._check_validators(),
            *self._check_deprecation_details(),
            *self._check_multiple(),
            *self._check_max_length_attribute(**kwargs),
        ]
