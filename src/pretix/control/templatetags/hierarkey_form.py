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
from django.template import Node
from django.utils.translation import gettext as _

from pretix.base.models import Event

register = template.Library()


class PropagatedNode(Node):
    def __init__(self, nodelist, event, field_names, url):
        self.nodelist = nodelist
        self.event = template.Variable(event)
        self.field_names = field_names
        self.url = template.Variable(url)

    def render(self, context):
        event = self.event.resolve(context)
        url = self.url.resolve(context)
        body = self.nodelist.render(context)

        if all([fn not in event.settings._cache() for fn in self.field_names]):
            body = """
            <div class="propagated-settings-box locked panel panel-default">
                <div class="panel-heading">
                    <input type="hidden" name="_settings_ignore" value="{fnames}">
                    <input type="hidden" name="decouple" value="">
                    <button type="button" class="btn btn-default pull-right btn-xs" value="{fnames}" data-action="unlink">
                        <span class="fa fa-unlock"></span> {text_unlink}
                    </button>
                    <h4 class="panel-title">
                        <span class="fa fa-lock"></span> {text_inh}
                    </h4>
                </div>
                <div class="panel-body help-text">
                    {text_expl}<br>
                    <a href="{url}" target="_blank" class="btn btn-default">
                        {text_orga}
                    </a>
                </div>
                <div class="panel-body propagated-settings-form">
                    {body}
                </div>
            </div>
            """.format(
                body=body,
                text_inh=_("Currently set on organizer level") if isinstance(event, Event) else _('Currently set on global level'),
                fnames=','.join(self.field_names),
                text_expl=_(
                    'These settings are currently set on organizer level. This way, you can easily change them for '
                    'all of your events at the same time. You can either go to the organizer settings to change them for all your events '
                    'or you can unlock them to change them for this event individually.'
                ) if isinstance(event, Event) else _(
                    'These settings are currently set on global level. This way, you can easily change them for '
                    'all organizers at the same time. You can either go to the global settings to change them for all your organizers '
                    'or you can unlock them to change them for this event individually.'
                ),
                text_unlink=_('Unlock'),
                text_orga=_('Go to organizer settings') if isinstance(event, Event) else _('Go to global settings'),
                url=url
            )

        return body


@register.tag
def propagated(parser, token):
    try:
        tag, event, url, *args = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            "%r tag requires at least three arguments" % token.contents.split()[0]
        )

    nodelist = parser.parse(('endpropagated',))
    parser.delete_first_token()
    return PropagatedNode(nodelist, event, [f[1:-1] for f in args], url)
