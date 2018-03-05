import json

import dateutil.parser
import pytz
from django.core.urlresolvers import resolve, reverse
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import CheckinList
from pretix.base.signals import logentry_display
from pretix.control.signals import nav_event


@receiver(nav_event, dispatch_uid="pretixdroid_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders'):
        return []
    return [
        {
            'label': _('Check-in devices'),
            'url': reverse('plugins:pretixdroid:config', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.namespace == 'plugins:pretixdroid' and url.url_name == 'config'),
            'icon': 'mobile',
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

    if 'list' in data:
        try:
            checkin_list = sender.checkin_lists.get(pk=data.get('list')).name
        except CheckinList.DoesNotExist:
            checkin_list = _("(unknown)")
    else:
        checkin_list = _("(unknown)")

    if data.get('first'):
        if show_dt:
            return _('Position #{posid} has been scanned at {datetime} for list "{list}".').format(
                posid=data.get('positionid'),
                datetime=dt_formatted,
                list=checkin_list
            )
        else:
            return _('Position #{posid} has been scanned for list "{list}".').format(
                posid=data.get('positionid'),
                list=checkin_list
            )
    else:
        if data.get('forced'):
            return _(
                'A scan for position #{posid} at {datetime} for list "{list}" has been uploaded even though it has '
                'been scanned already.'.format(
                    posid=data.get('positionid'),
                    datetime=dt_formatted,
                    list=checkin_list
                )
            )
        return _(
            'Position #{posid} has been scanned and rejected because it has already been scanned before '
            'on list "{list}".'.format(
                posid=data.get('positionid'),
                list=checkin_list
            )
        )
