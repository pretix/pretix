from i18nfield.strings import LazyI18nString

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Event, InvoiceAddress, Order, User
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.tasks import ProfiledEventTask
from pretix.celery_app import app


@app.task(base=ProfiledEventTask, acks_late=True)
def send_mails(event: Event, user: int, subject: dict, message: dict, orders: list, items: list,
               recipients: str, filter_checkins: bool, not_checked_in: bool, checkin_lists: list,
               attachments: list = None) -> None:
    failures = []
    user = User.objects.get(pk=user) if user else None
    orders = Order.objects.filter(pk__in=orders, event=event)
    subject = LazyI18nString(subject)
    message = LazyI18nString(message)

    for o in orders:
        send_to_order = recipients in ('both', 'orders')

        try:
            ia = o.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = InvoiceAddress(order=o)

        if recipients in ('both', 'attendees'):
            for p in o.positions.prefetch_related('addons'):
                if p.addon_to_id is not None:
                    continue

                if p.item_id not in items and not any(a.item_id in items for a in p.addons.all()):
                    continue

                if filter_checkins:
                    checkins = list(p.checkins.all())
                    allowed = (
                        (not_checked_in and not checkins)
                        or (any(c.list_id in checkin_lists for c in checkins))
                    )
                    if not allowed:
                        continue

                if not p.attendee_email:
                    if recipients == 'attendees':
                        send_to_order = True
                    continue

                if p.attendee_email == o.email and send_to_order:
                    continue

                try:
                    with language(o.locale):
                        email_context = get_email_context(event=event, order=o, position_or_address=p, position=p)
                        mail(
                            p.attendee_email,
                            subject,
                            message,
                            email_context,
                            event,
                            locale=o.locale,
                            order=o,
                            position=p,
                            attach_cached_files=attachments
                        )
                        o.log_action(
                            'pretix.plugins.sendmail.order.email.sent.attendee',
                            user=user,
                            data={
                                'position': p.positionid,
                                'subject': subject.localize(o.locale).format_map(email_context),
                                'message': message.localize(o.locale).format_map(email_context),
                                'recipient': p.attendee_email
                            }
                        )
                except SendMailException:
                    failures.append(p.attendee_email)

        if send_to_order and o.email:
            try:
                with language(o.locale):
                    email_context = get_email_context(event=event, order=o, position_or_address=ia)
                    mail(
                        o.email,
                        subject,
                        message,
                        email_context,
                        event,
                        locale=o.locale,
                        order=o
                    )
                    o.log_action(
                        'pretix.plugins.sendmail.order.email.sent',
                        user=user,
                        data={
                            'subject': subject.localize(o.locale).format_map(email_context),
                            'message': message.localize(o.locale).format_map(email_context),
                            'recipient': o.email
                        }
                    )
            except SendMailException:
                failures.append(o.email)
