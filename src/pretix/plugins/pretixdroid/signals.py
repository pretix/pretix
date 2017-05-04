import json

import dateutil.parser
import pytz
from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import logentry_display
from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="pretixdroid_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders'):
        return []
    return [
        {
            'label': _('pretixdroid'),
            'url': reverse('plugins:pretixdroid:config', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:pretixdroid' and url.url_name == 'config'),
            'icon': 'android',
        }
    ]


@receiver(signal=logentry_display, dispatch_uid="pretixdroid_logentry_display")
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    if logentry.action_type != 'pretix.plugins.pretixdroid.scan':
        return

    data = json.loads(logentry.data)

    show_dt = False
    if 'datetime' in data:
        dt = dateutil.parser.parse(data.get('datetime'))
        show_dt = abs((logentry.datetime - dt).total_seconds()) > 60 or 'forced' in data
        tz = pytz.timezone(sender.settings.timezone)
        dt_formatted = date_format(dt.astimezone(tz), "SHORT_DATETIME_FORMAT")

    if data.get('first'):
        if show_dt:
            return _('Position #{posid} has been scanned at {datetime}.').format(
                posid=data.get('positionid'),
                datetime=dt_formatted
            )
        else:
            return _('Position #{posid} has been scanned.').format(
                posid=data.get('positionid')
            )
    else:
        if data.get('forced'):
            return _(
                'A scan for position #{posid} at {datetime} has been uploaded even though it has '
                'been scanned already.'.format(
                    posid=data.get('positionid'),
                    datetime=dt_formatted
                )
            )
        return _('Position #{posid} has been scanned and rejected because it has already been scanned before.'.format(
            posid=data.get('positionid')
        ))
