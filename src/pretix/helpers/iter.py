#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import itertools


def chunked_iterable(iterable, size):
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk


def sort_groupby(data, group_key, inner_sort_key=None):
    """
    Groups data by group_key, returns a list of (group_key, list). The outer list is
    sorted by group_key, all inner lists are sorted by inner_sort_key.
    """
    sort_key = group_key if inner_sort_key is None else lambda d: (group_key(d), inner_sort_key(d))
    return [(group, list(items)) for group, items in itertools.groupby(sorted(data, key=sort_key), group_key)]


def sort_groupby_exp(data, group_key, inner_sort_key=None):
    """
    Same as sort_groupby, but items are passed into the key functions as *item, so tuples can be destructed easily.
    """
    sort_key = (lambda d: group_key(*d)) if inner_sort_key is None else lambda d: (group_key(*d), inner_sort_key(*d))
    return [(group, list(items)) for group, items in itertools.groupby(sorted(data, key=sort_key), lambda d: group_key(*d))]
