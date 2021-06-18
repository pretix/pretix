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
from django.conf import settings
from django.template import Library, Node, TemplateSyntaxError, Variable
from django.templatetags.cache import CacheNode

register = Library()


class DummyNode(Node):
    def __init__(self, nodelist, *args):
        self.nodelist = nodelist

    def render(self, context):
        value = self.nodelist.render(context)
        return value


@register.tag('cache_large')
def do_cache(parser, token):
    nodelist = parser.parse(('endcache_large',))
    parser.delete_first_token()
    tokens = token.split_contents()
    if len(tokens) < 3:
        raise TemplateSyntaxError("'%r' tag requires at least 2 arguments." % tokens[0])

    if not settings.CACHE_LARGE_VALUES_ALLOWED:
        return DummyNode(
            nodelist,
        )

    return CacheNode(
        nodelist, parser.compile_filter(tokens[1]),
        tokens[2],  # fragment_name can't be a variable.
        [parser.compile_filter(t) for t in tokens[3:]],
        Variable(repr(settings.CACHE_LARGE_VALUES_ALIAS)),
    )
