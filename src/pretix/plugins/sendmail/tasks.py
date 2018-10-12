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
def send_mails(event: int, user: int, subject: dict, message: dict, orders: list) -> None:
    failures = []
    event = Event.objects.get(pk=event)
    user = User.objects.get(pk=user) if user else None
    orders = Order.objects.filter(pk__in=orders)
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
        try:
            with language(o.locale):
                email_context = {
                    'event': o.event,
                    'code': o.code,
                    'date': date_format(o.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                    'expire_date': date_format(o.expires, 'SHORT_DATE_FORMAT'),
                    'url': build_absolute_uri(event, 'presale:event.order', kwargs={
                        'order': o.code,
                        'secret': o.secret
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
