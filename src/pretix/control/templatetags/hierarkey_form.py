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
            <div class="propagated-settings-box">
                <input type="hidden" name="_settings_ignore" value="{fnames}">
                <div class="propagated-settings-form blurred">
                    {body}
                </div>
                <div class="propagated-settings-overlay">
                    <h4><span class="fa fa-link"></span> {text_inh}</h4>
                    <p>
                        {text_expl}
                    </p>
                    <button class="btn btn-default" name="decouple" value="{fnames}" data-action="unlink">
                        <span class="fa fa-unlink"></span> {text_unlink}
                    </button>
                    <a class="btn btn-default" href="{url}" target="_blank">
                        <span class="fa fa-group"></span> {text_orga}
                    </a>
                </div>
            </div>
            """.format(
                body=body,
                text_inh=_("Organizer-level settings") if isinstance(event, Event) else _('Site-level settings'),
                fnames=','.join(self.field_names),
                text_expl=_(
                    'These settings are currently set on organizer level. This way, you can easily change them for '
                    'all of your events at the same time. You can either go to the organizer settings to change them '
                    'or decouple them from the organizer account to change them for this event individually.'
                ) if isinstance(event, Event) else _(
                    'These settings are currently set on global level. This way, you can easily change them for '
                    'all organizers at the same time. You can either go to the global settings to change them '
                    'or decouple them from the global settings to change them for this event individually.'
                ),
                text_unlink=_('Change only for this event') if isinstance(event, Event) else _('Change only for this organizer'),
                text_orga=_('Change for all events') if isinstance(event, Event) else _('Change for all organizers'),
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
