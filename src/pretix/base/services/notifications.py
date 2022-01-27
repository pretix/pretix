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
import css_inline
from django.conf import settings
from django.template.loader import get_template
from django.utils.timezone import override
from django_scopes import scope, scopes_disabled

from pretix.base.i18n import language
from pretix.base.models import LogEntry, NotificationSetting, User
from pretix.base.notifications import Notification, get_all_notification_types
from pretix.base.services.mail import mail_send_task
from pretix.base.services.tasks import ProfiledTask, TransactionAwareTask
from pretix.celery_app import app
from pretix.helpers.urls import build_absolute_uri


@app.task(base=TransactionAwareTask, acks_late=True, max_retries=9, default_retry_delay=900)
@scopes_disabled()
def notify(logentry_ids: list):
    if not isinstance(logentry_ids, list):
        logentry_ids = [logentry_ids]

    qs = LogEntry.all.select_related('event', 'event__organizer').filter(id__in=logentry_ids)

    _event, _at, notify_specific, notify_global = None, None, None, None
    for logentry in qs:
        if not logentry.event:
            break  # Ignore, we only have event-related notifications right now

        notification_type = logentry.notification_type

        if not notification_type:
            break  # No suitable plugin

        if _event != logentry.event or _at != logentry.action_type or notify_global is None:
            _event = logentry.event
            _at = logentry.action_type
            # All users that have the permission to get the notification
            users = logentry.event.get_users_with_permission(
                notification_type.required_permission
            ).filter(notifications_send=True, is_active=True)
            if logentry.user:
                users = users.exclude(pk=logentry.user.pk)

            # Get all notification settings, both specific to this event as well as global
            notify_specific = {
                (ns.user, ns.method): ns.enabled
                for ns in NotificationSetting.objects.filter(
                    event=logentry.event,
                    action_type=notification_type.action_type,
                    user__pk__in=users.values_list('pk', flat=True)
                )
            }
            notify_global = {
                (ns.user, ns.method): ns.enabled
                for ns in NotificationSetting.objects.filter(
                    event__isnull=True,
                    action_type=notification_type.action_type,
                    user__pk__in=users.values_list('pk', flat=True)
                )
            }

        for um, enabled in notify_specific.items():
            user, method = um
            if enabled:
                send_notification.apply_async(args=(logentry.id, notification_type.action_type, user.pk, method))

        for um, enabled in notify_global.items():
            user, method = um
            if enabled and um not in notify_specific:
                send_notification.apply_async(args=(logentry.id, notification_type.action_type, user.pk, method))


@app.task(base=ProfiledTask, acks_late=True, max_retries=9, default_retry_delay=900)
def send_notification(logentry_id: int, action_type: str, user_id: int, method: str):
    logentry = LogEntry.all.get(id=logentry_id)
    if logentry.event:
        sm = lambda: scope(organizer=logentry.event.organizer)  # noqa
    else:
        sm = lambda: scopes_disabled()  # noqa
    with sm():
        user = User.objects.get(id=user_id)
        types = get_all_notification_types(logentry.event)
        notification_type = types.get(action_type)
        if not notification_type:
            return  # Ignore, e.g. plugin not active for this event

        with language(user.locale), override(logentry.event.timezone if logentry.event else user.timezone):
            notification = notification_type.build_notification(logentry)

            if method == "mail":
                send_notification_mail(notification, user)


def send_notification_mail(notification: Notification, user: User):
    ctx = {
        'site': settings.PRETIX_INSTANCE_NAME,
        'site_url': settings.SITE_URL,
        'color': settings.PRETIX_PRIMARY_COLOR,
        'notification': notification,
        'settings_url': build_absolute_uri(
            'control:user.settings.notifications',
        ),
        'disable_url': build_absolute_uri(
            'control:user.settings.notifications.off',
            kwargs={
                'token': user.notifications_token,
                'id': user.pk
            }
        )
    }

    tpl_html = get_template('pretixbase/email/notification.html')

    body_html = tpl_html.render(ctx)
    inliner = css_inline.CSSInliner(remove_style_tags=True)
    body_html = inliner.inline(body_html)

    tpl_plain = get_template('pretixbase/email/notification.txt')
    body_plain = tpl_plain.render(ctx)

    mail_send_task.apply_async(kwargs={
        'to': [user.email],
        'subject': '[{}] {}: {}'.format(
            settings.PRETIX_INSTANCE_NAME,
            notification.event.settings.mail_prefix or notification.event.slug.upper(),
            notification.title
        ),
        'body': body_plain,
        'html': body_html,
        'sender': settings.MAIL_FROM_NOTIFICATIONS,
        'headers': {},
        'user': user.pk
    })
