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

from typing import List, Tuple

from pretix.base.datasync.datasync import (
    MODE_APPEND_LIST, MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW,
    SyncConfigError,
)


def assign_properties(
    new_values: List[Tuple[str, str, str]], old_values: dict, is_new=True, list_sep=";",
):
    out = {}

    for k, v, mode in new_values:
        if mode == MODE_OVERWRITE:
            out[k] = v
            continue
        elif mode == MODE_SET_IF_NEW and not is_new:
            continue
        if not v:
            continue

        current_value = old_values.get(k, out.get(k, ""))
        if mode in (MODE_SET_IF_EMPTY, MODE_SET_IF_NEW):
            if not current_value:
                out[k] = v
        elif mode == MODE_APPEND_LIST:
            _add_to_list(out, k, current_value, v, list_sep)
        else:
            raise SyncConfigError(["Invalid update mode " + mode])
    return out


def _add_to_list(out, key, current_value, new_item, list_sep):
    new_item = str(new_item)
    if list_sep is not None:
        new_item = new_item.replace(list_sep, "")
        current_value = current_value.split(list_sep) if current_value else []
    else:
        current_value = list(current_value)
    if new_item not in current_value:
        new_list = current_value + [new_item]
        if list_sep is not None:
            new_list = list_sep.join(new_list)
        out[key] = new_list
