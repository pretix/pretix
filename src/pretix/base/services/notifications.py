from django.conf import settings
from django.template.loader import get_template
from inlinestyler.utils import inline_css

from pretix.base.i18n import language
from pretix.base.models import LogEntry, NotificationSetting, User
from pretix.base.notifications import Notification, get_all_notification_types
from pretix.base.services.mail import mail_send_task
from pretix.base.services.tasks import ProfiledTask, TransactionAwareTask
from pretix.celery_app import app
from pretix.helpers.urls import build_absolute_uri


@app.task(base=TransactionAwareTask)
def notify(logentry_id: int):
    logentry = LogEntry.all.get(id=logentry_id)
    if not logentry.event:
        return  # Ignore, we only have event-related notifications right now
    types = get_all_notification_types(logentry.event)

    notification_type = None
    typepath = logentry.action_type
    while not notification_type and '.' in typepath:
        notification_type = types.get(typepath + ('.*' if typepath != logentry.action_type else ''))
        typepath = typepath.rsplit('.', 1)[0]

    if not notification_type:
        return  # No suitable plugin

    # All users that have the permission to get the notification
    users = logentry.event.get_users_with_permission(
        notification_type.required_permission
    ).filter(notifications_send=True)
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
            send_notification.apply_async(args=(logentry_id, notification_type.action_type, user.pk, method))

    for um, enabled in notify_global.items():
        user, method = um
        if enabled and um not in notify_specific:
            send_notification.apply_async(args=(logentry_id, notification_type.action_type, user.pk, method))


@app.task(base=ProfiledTask)
def send_notification(logentry_id: int, action_type: str, user_id: int, method: str):
    logentry = LogEntry.all.get(id=logentry_id)
    user = User.objects.get(id=user_id)
    types = get_all_notification_types(logentry.event)
    notification_type = types.get(action_type)
    if not notification_type:
        return  # Ignore, e.g. plugin not active for this event

    with language(user.locale):
        notification = notification_type.build_notification(logentry)

        if method == "mail":
            send_notification_mail(notification, user)


def send_notification_mail(notification: Notification, user: User):
    ctx = {
        'site': settings.PRETIX_INSTANCE_NAME,
        'site_url': settings.SITE_URL,
        'color': '#8E44B3',
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
    body_html = inline_css(tpl_html.render(ctx))
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
        'sender': settings.MAIL_FROM,
        'headers': {},
    })
