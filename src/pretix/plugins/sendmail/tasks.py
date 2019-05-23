import pytz
from django.utils.formats import date_format
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import Event, InvoiceAddress, Order, User
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.tasks import ProfiledTask
from pretix.celery_app import app
from pretix.multidomain.urlreverse import build_absolute_uri


@app.task(base=ProfiledTask)
def send_mails(event: int, user: int, subject: dict, message: dict, orders: list, items: list, recipients: str) -> None:
    failures = []
    event = Event.objects.get(pk=event)
    user = User.objects.get(pk=user) if user else None
    orders = Order.objects.filter(pk__in=orders, event=event)
    subject = LazyI18nString(subject)
    message = LazyI18nString(message)
    tz = pytz.timezone(event.settings.timezone)

    for o in orders:
        try:
            invoice_name = o.invoice_address.name
            invoice_company = o.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""

        send_to_order = recipients in ('both', 'orders')
        if recipients in ('both', 'attendees'):
            for p in o.positions.prefetch_related('addons'):
                if p.addon_to_id is not None:
                    continue

                if p.item_id not in items and not any(a.item_id in items for a in p.addons.all()):
                    continue

                if not p.attendee_email:
                    if recipients == 'attendees':
                        send_to_order = True
                    continue

                if p.attendee_email == o.email and send_to_order:
                    continue

                try:
                    with language(o.locale):
                        email_context = {
                            'event': event,
                            'code': o.code,
                            'date': date_format(o.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                            'expire_date': date_format(o.expires, 'SHORT_DATE_FORMAT'),
                            'url': build_absolute_uri(event, 'presale:event.order.position', kwargs={
                                'order': o.code,
                                'secret': p.web_secret,
                                'position': p.positionid
                            }),
                            'invoice_name': invoice_name,
                            'invoice_company': invoice_company,
                        }
                        mail(
                            p.attendee_email,
                            subject,
                            message,
                            email_context,
                            event,
                            locale=o.locale,
                            order=o,
                            position=p
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
                    email_context = {
                        'event': event,
                        'code': o.code,
                        'date': date_format(o.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                        'expire_date': date_format(o.expires, 'SHORT_DATE_FORMAT'),
                        'url': build_absolute_uri(event, 'presale:event.order.open', kwargs={
                            'order': o.code,
                            'secret': o.secret,
                            'hash': o.email_confirm_hash()
                        }),
                        'invoice_name': invoice_name,
                        'invoice_company': invoice_company,
                    }
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
