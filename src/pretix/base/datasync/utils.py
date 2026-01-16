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
from typing import List, Tuple

from pretix.base.datasync.datasync import SyncConfigError
from pretix.base.models.datasync import (
    MODE_APPEND_LIST, MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW,
)


def assign_properties(
    new_values: List[Tuple[str, str, str]], old_values: dict, is_new, list_sep
):
    """
    Generates a dictionary mapping property keys to new values, handling conditional overwrites and list updates
    according to an update mode specified per property.

    Supported update modes are:
     - `MODE_OVERWRITE`:  Replaces the existing value with the new value.
     - `MODE_SET_IF_NEW`: Only sets the property if `is_new` is True.
     - `MODE_SET_IF_EMPTY`: Only sets the property if the field is empty or missing in old_values.
     - `MODE_APPEND_LIST`: Appends the new value to the list from old_values (or the empty list if missing),
                           using `list_sep` as a separator.

    :param new_values: List of tuples, where each tuple contains (field_name, new_value, update_mode).
    :param old_values: Dictionary, current property values in the external system.
    :param is_new: Boolean, whether the object will be newly created in the external system.
    :param list_sep: If string, used as a separator for MODE_APPEND_LIST. If None, native lists are used.
    :raises SyncConfigError: If an invalid update mode is specified.
    :returns: A dictionary containing the properties that need to be updated in the external system.
    """

    out = {}

    for field_name, new_value, update_mode in new_values:
        if update_mode == MODE_OVERWRITE:
            out[field_name] = new_value
            continue
        elif update_mode == MODE_SET_IF_NEW and not is_new:
            continue
        if not new_value:
            continue

        current_value = old_values.get(field_name, out.get(field_name, ""))
        if update_mode in (MODE_SET_IF_EMPTY, MODE_SET_IF_NEW):
            if not current_value:
                out[field_name] = new_value
        elif update_mode == MODE_APPEND_LIST:
            _add_to_list(out, field_name, current_value, new_value, list_sep)
        else:
            raise SyncConfigError(["Invalid update mode " + update_mode])
    return out


def _add_to_list(out, field_name, current_value, new_item_input, list_sep):
    if list_sep is not None:
        new_items = str(new_item_input).split(list_sep)
        current_value = current_value.split(list_sep) if current_value else []
    else:
        new_items = [str(new_item_input)]
        if not isinstance(current_value, (list, tuple)):
            current_value = [str(current_value)]

    new_list = list(current_value)
    for new_item in new_items:
        if new_item not in current_value:
            new_list.append(new_item)
    if new_list != current_value:
        if list_sep is not None:
            new_list = list_sep.join(new_list)
        out[field_name] = new_list


def translate_property_mappings(property_mappings, checkin_list_map):
    """
    To properly handle copied events, users of data fields as provided by get_data_fields need to register to the
    event_copy_data signal and translate all stored references to those fields using this method.

    For example, if you store your mappings in a custom Django model with a ForeignKey to Event:

    .. code-block:: python

        @receiver(signal=event_copy_data, dispatch_uid="my_sync_event_copy_data")
        def event_copy_data_receiver(sender, other, checkin_list_map, **kwargs):
            object_mappings = other.my_object_mappings.all()
            object_mapping_map = {}
            for om in object_mappings:
                om = copy.copy(om)
                object_mapping_map[om.pk] = om
                om.pk = None
                om.event = sender
                om.property_mappings = translate_property_mappings(om.property_mappings, checkin_list_map)
                om.save()

    """
    mappings = []

    for mapping in property_mappings:
        pretix_field = mapping["pretix_field"]
        if pretix_field.startswith("checkin_date_"):
            old_id = int(pretix_field[len("checkin_date_"):])
            if old_id not in checkin_list_map:
                # old_id might not be in checkin_list_map, because copying of an event series only copies check-in
                # lists covering the whole series, not individual dates.
                pretix_field = "_invalid_" + pretix_field
            else:
                pretix_field = "checkin_date_%d" % checkin_list_map[old_id].pk
        mappings.append({**mapping, "pretix_field": pretix_field})
    return mappings
