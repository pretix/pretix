import logging

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import get_template
from django.utils.translation import ugettext as _
from typing import Any, Dict

from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import Event

logger = logging.getLogger('pretix.base.mail')


class TolerantDict(dict):

    def __missing__(self, key):
        return key


def mail(email: str, subject: str, template: str,
         context: Dict[str, Any]=None, event: Event=None, locale: str=None):
    """
    Sends out an email to a user. The mail will be sent synchronously or asynchronously depending on the installation.

    :param email: The e-mail address of the recipient.

    :param subject: The e-mail subject. Should be localized to the recipients's locale or a lazy object that will be
        localized by being casted to a string.

    :param template: The filename of a template to be used. It will be rendered with the locale given in the locale
        argument and the context given in the next argument. Alternatively, you can pass a LazyI18nString and
        ``context`` will be used as the argument to a  Python ``.format()`` call on the template.

    :param context: The context for rendering the template (see ``template`` parameter).

    :param event: The event this email is related to (optional). If set, this will be used to determine the sender,
        a possible prefix for the subject and the SMTP server that should be used to send this email.

    :param locale: The locale to be used while evaluating the subject and the template.

    :return: ``False`` on obvious, immediate failures, ``True`` otherwise. ``True`` does not necessarily mean that
        the email has been sent, just that it has been queued by the e-mail backend.
    """
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

            body += "\r\n\r\n----\r\n"
            body += _(
                "You are receiving this e-mail because you placed an order for {event}."
            ).format(event=event.name)
            body += "\r\n"
        return mail_send([email], subject, body, sender, event.id if event else None)


def mail_send(to: str, subject: str, body: str, sender: str, event: int=None) -> bool:
    email = EmailMessage(subject, body, sender, to=to)
    if event:
        event = Event.objects.get(id=event)
        backend = event.get_mail_backend()
    else:
        backend = get_connection(fail_silently=False)

    try:
        backend.send_messages([email])
        return True
    except Exception:
        logger.exception('Error sending e-mail')
        return False


if settings.HAS_CELERY and settings.EMAIL_BACKEND != 'django.core.mail.outbox':
    from pretix.celery import app

    mail_send_task = app.task(mail_send)

    def mail_send(*args, **kwargs):
        mail_send_task.apply_async(args=args, kwargs=kwargs)
