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
from django import template
from django.template import TemplateSyntaxError
from django.template.base import kwarg_re
from django.template.defaulttags import URLNode
from django.urls import NoReverseMatch
from django.utils.encoding import smart_str
from django.utils.html import conditional_escape

from pretix.multidomain.urlreverse import build_absolute_uri, mainreverse

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
        event = self.event.resolve(context) if self.event is not False else False
        url = ''
        try:
            if self.absolute:
                url = build_absolute_uri(event, view_name, kwargs=kwargs)
            elif self.event is False:
                url = mainreverse(view_name, kwargs)
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


def multidomainurl(parser, token, has_event, absolute):
    """
    Similar to {% url %}, but multidomain-aware. Used by eventurl, abseventurl and absmainurl.

    If has_event=True, takes an event or organizer object as first template tag parameter.
    Always takes an url name and optional keyword arguments after that.

    Returns an absolute URL in the following cases:
    - absolute=True
    - has_event=True and the event has a custom domain
    Returns a relative URL otherwise.
    """
    bits = token.split_contents()
    tagname = bits[0]
    if has_event:
        if len(bits) < 3:
            raise TemplateSyntaxError("'%s' takes at least two arguments, an event and the name of a url()." % tagname)
        viewname = parser.compile_filter(bits[2])
        event = parser.compile_filter(bits[1])
        bits = bits[3:]
    else:
        if len(bits) < 2:
            raise TemplateSyntaxError("'%s' takes at least one arguments, the name of a url()." % tagname)
        viewname = parser.compile_filter(bits[1])
        event = False
        bits = bits[2:]
    kwargs = {}
    asvar = None
    if len(bits) >= 2 and bits[-2] == 'as':
        asvar = bits[-1]
        bits = bits[:-2]

    if bits:
        for bit in bits:
            match = kwarg_re.match(bit)
            if not match:
                raise TemplateSyntaxError("Malformed arguments to %s tag" % tagname)
            name, value = match.groups()
            if name:
                kwargs[name] = parser.compile_filter(value)
            else:
                raise TemplateSyntaxError('Multidomain urls only have keyword arguments.')

    return EventURLNode(event, viewname, kwargs, asvar, absolute)


@register.tag
def eventurl(parser, token):
    """
    Similar to {% url %} in the same way that eventreverse() is similar to reverse().

    Takes an event or organizer object, an url name and optional keyword arguments
    """
    return multidomainurl(parser, token, has_event=True, absolute=False)


@register.tag
def abseventurl(parser, token):
    """
    Similar to {% url %} in the same way that eventreverse() is similar to reverse().

    Returns an absolute URL.
    """
    return multidomainurl(parser, token, has_event=True, absolute=True)


@register.tag
def absmainurl(parser, token):
    """
    Like {% url %}, but always returns an absolute URL on the main domain.
    """
    return multidomainurl(parser, token, has_event=False, absolute=True)
