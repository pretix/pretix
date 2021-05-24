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
import json

from django import template
from django.template.defaultfilters import stringfilter

from pretix.helpers.escapejson import escapejson, escapejson_attr

register = template.Library()


@register.filter("escapejson")
@stringfilter
def escapejs_filter(value):
    """Hex encodes characters for use in a application/json type script."""
    return escapejson(value)


@register.filter("escapejson_dumps")
def escapejs_dumps_filter(value):
    """Hex encodes characters for use in a application/json type script."""
    return escapejson(json.dumps(value))


@register.filter("attr_escapejson_dumps")
def attr_escapejs_dumps_filter(value):
    """Hex encodes characters for use in an HTML attribute."""
    return escapejson_attr(json.dumps(value))
