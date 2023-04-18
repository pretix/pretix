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
from babel.core import Locale
from django.core.cache import cache
from django.utils import translation
from django_countries import Countries, collator
from django_countries.fields import CountryField
from phonenumbers.data import _COUNTRY_CODE_TO_REGION_CODE

from pretix.base.i18n import get_babel_locale, get_language_without_region


class CachedCountries(Countries):
    _cached_lists = {}
    cache_subkey = None

    def __iter__(self):
        """
        Iterate through countries, sorted by name, but cache the results based on the locale.
        django-countries performs a unicode-aware sorting based on pyuca which is incredibly
        slow.
        """
        cache_key = "countries:all:{}".format(get_language_without_region())
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


_cached_phone_prefixes = {}


def get_phone_prefixes_sorted_and_localized():
    language = get_babel_locale()  # changed from default implementation that used the django locale

    cache_key = "phoneprefixes:all:{}".format(language)
    if cache_key in _cached_phone_prefixes:
        return _cached_phone_prefixes[cache_key]

    val = cache.get(cache_key)
    if val:
        _cached_phone_prefixes[cache_key] = val
        return val

    val = []

    locale = Locale(translation.to_locale(language))
    for prefix, values in _COUNTRY_CODE_TO_REGION_CODE.items():
        prefix = "+%d" % prefix
        for country_code in values:
            country_name = locale.territories.get(country_code)
            if country_name:
                val.append((prefix, "{} {}".format(country_name, prefix)))

    val = sorted(val, key=lambda item: collator.sort_key(item[1]))

    _cached_phone_prefixes[cache_key] = val
    cache.set(cache_key, val, 3600 * 24 * 30)
    return val
