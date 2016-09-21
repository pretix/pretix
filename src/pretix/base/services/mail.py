import logging
from typing import Any, Dict

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import get_template
from django.utils.translation import ugettext as _

from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import Event, Order
from pretix.celery import app
from pretix.multidomain.urlreverse import build_absolute_uri

logger = logging.getLogger('pretix.base.mail')
INVALID_ADDRESS = 'invalid-pretix-mail-address'


class TolerantDict(dict):

    def __missing__(self, key):
        return key


class SendMailException(Exception):
    pass


def mail(email: str, subject: str, template: str,
         context: Dict[str, Any]=None, event: Event=None, locale: str=None,
         order: Order=None, headers: dict=None):
    """
    Sends out an email to a user. The mail will be sent synchronously or asynchronously depending on the installation.

    :param email: The email address of the recipient

    :param subject: The email subject. Should be localized to the recipients's locale or a lazy object that will be
        localized by being casted to a string.

    :param template: The filename of a template to be used. It will be rendered with the locale given in the locale
        argument and the context given in the next argument. Alternatively, you can pass a LazyI18nString and
        ``context`` will be used as the argument to a  Python ``.format()`` call on the template.

    :param context: The context for rendering the template (see ``template`` parameter)

    :param event: The event this email is related to (optional). If set, this will be used to determine the sender,
        a possible prefix for the subject and the SMTP server that should be used to send this email.

    :param order: The order this email is related to (optional). If set, this will be used to include a link to the
        order below the email.

    :param headers: A dict of custom mail headers to add to the mail

    :param locale: The locale to be used while evaluating the subject and the template

    :raises MailOrderException: on obvious, immediate failures. Not raising an exception does not necessarily mean
        that the email has been sent, just that it has been queued by the email backend.
    """
    if email == INVALID_ADDRESS:
        return

    with language(locale):
        if isinstance(template, LazyI18nString):
            body = str(template)
            if context:
                body = body.format_map(TolerantDict(context))
        else:
            tpl = get_template(template)
            body = tpl.render(context)

        sender = event.settings.get('mail_from') if event else settings.MAIL_FROM

        subject = str(subject)
        if event:
            prefix = event.settings.get('mail_prefix')
            if prefix:
                subject = "[%s] %s" % (prefix, subject)

            body += "\r\n\r\n-- \r\n"
            body += _(
                "You are receiving this email because you placed an order for {event}."
            ).format(event=event.name)
            if order:
                body += "\r\n"
                body += _(
                    "You can view your order details at the following URL:\r\n{orderurl}."
                ).format(event=event.name, orderurl=build_absolute_uri(order.event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }))
            body += "\r\n"
        return mail_send([email], subject, body, sender, event.id if event else None, headers)


@app.task
def mail_send_task(to: str, subject: str, body: str, sender: str, event: int=None, headers: dict=None) -> bool:
    email = EmailMessage(subject, body, sender, to=to, headers=headers)
    if event:
        event = Event.objects.get(id=event)
        backend = event.get_mail_backend()
    else:
        backend = get_connection(fail_silently=False)

    try:
        backend.send_messages([email])
    except Exception:
        logger.exception('Error sending email')
        raise SendMailException('Failed to send an email to {}.'.format(to))


def mail_send(*args, **kwargs):
    mail_send_task.apply_async(args=args, kwargs=kwargs)
