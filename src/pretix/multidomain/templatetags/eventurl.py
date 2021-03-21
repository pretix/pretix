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
from django import template
from django.template import TemplateSyntaxError
from django.template.base import kwarg_re
from django.template.defaulttags import URLNode
from django.urls import NoReverseMatch
from django.utils.encoding import smart_str
from django.utils.html import conditional_escape

from pretix.multidomain.urlreverse import build_absolute_uri

register = template.Library()


class EventURLNode(URLNode):
    def __init__(self, event, view_name, kwargs, asvar, absolute):
        self.event = event
        self.absolute = absolute
        super().__init__(view_name, [], kwargs, asvar)

    def render(self, context):
        from pretix.multidomain.urlreverse import eventreverse
        kwargs = {
            smart_str(k, 'ascii'): v.resolve(context)
            for k, v in self.kwargs.items()
        }
        view_name = self.view_name.resolve(context)
        event = self.event.resolve(context)
        url = ''
        try:
            if self.absolute:
                url = build_absolute_uri(event, view_name, kwargs=kwargs)
            else:
                url = eventreverse(event, view_name, kwargs=kwargs)
        except NoReverseMatch:
            if self.asvar is None:
                raise

        if self.asvar:
            context[self.asvar] = url
            return ''
        else:
            if context.autoescape:
                url = conditional_escape(url)
            return url


@register.tag
def eventurl(parser, token, absolute=False):
    """
    Similar to {% url %} in the same way that eventreverse() is similar to reverse().

    Takes an event or organizer object, an url name and optional keyword arguments
    """
    bits = token.split_contents()
    if len(bits) < 3:
        raise TemplateSyntaxError("'%s' takes at least two arguments, an event and the name of a url()." % bits[0])
    viewname = parser.compile_filter(bits[2])
    event = parser.compile_filter(bits[1])
    kwargs = {}
    asvar = None
    bits = bits[3:]
    if len(bits) >= 2 and bits[-2] == 'as':
        asvar = bits[-1]
        bits = bits[:-2]

    if bits:
        for bit in bits:
            match = kwarg_re.match(bit)
            if not match:
                raise TemplateSyntaxError("Malformed arguments to eventurl tag")
            name, value = match.groups()
            if name:
                kwargs[name] = parser.compile_filter(value)
            else:
                raise TemplateSyntaxError('Event urls only have keyword arguments.')

    return EventURLNode(event, viewname, kwargs, asvar, absolute)


@register.tag
def abseventurl(parser, token):
    """
    Similar to {% url %} in the same way that eventreverse() is similar to reverse().

    Returns an absolute URL.
    """
    return eventurl(parser, token, absolute=True)
