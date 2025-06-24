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
import urllib.parse


def _add_params(url, params):
    url_parts = list(urllib.parse.urlparse(url))
    query = urllib.parse.parse_qs(url_parts[4])
    query = [*query, *params]
    url_parts[4] = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse(url_parts)


def _find_field_names(d: dict, path):
    names = set()
    for k, v in d.items():
        if isinstance(v, dict):
            names |= _find_field_names(v, path=(*path, k))
        elif isinstance(v, list) and len(v) > 0:
            names |= _find_field_names(v[0], path=(*path, k))
        else:
            names.add(".".join([*path, k]))
    return names


def _test_configurable_serializer(client, url, field_name_samples, expands):
    # Test include
    resp = client.get(_add_params(url, [("include", f) for f in field_name_samples]))
    if "results" in resp.data:
        o = resp.data["results"][0]
    else:
        o = resp.data

    found_field_names = _find_field_names(o, tuple())
    # Assert no unexpected fields
    for f in found_field_names:
        depth = f.count(".")
        assert f in field_name_samples or any(f.rsplit(".", c)[0] in field_name_samples for c in range(depth))
    # Assert all fields are there
    for f in field_name_samples:
        assert f in found_field_names

    # Test exclude
    resp = client.get(_add_params(url, [("exclude", f) for f in field_name_samples]))
    if "results" in resp.data:
        o = resp.data["results"][0]
    else:
        o = resp.data
    found_field_names = _find_field_names(o, [])
    # Assert all fields are not there
    for f in found_field_names:
        assert f not in field_name_samples

    # Test expand
    if expands:
        resp = client.get(_add_params(url, [("expand", f) for f in expands]))
        if "results" in resp.data:
            o = resp.data["results"][0]
        else:
            o = resp.data
        for e in expands:
            path = e.split(".")
            obj = o
            while len(path) > 1:
                obj = o[path[0]]
                if isinstance(obj, list):
                    obj = obj[0]
                path = path[1:]
            assert isinstance(obj[path[0]], dict)
