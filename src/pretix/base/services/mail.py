import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.utils import translation
from django.utils.translation import ugettext as _

from pretix.base.i18n import LazyI18nString
from pretix.base.models import Event, User
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger('pretix.base.mail')


def mail(user: User, subject: str, template: str, context: dict=None, event: Event=None):
    """
    Sends out an email to a user.

    :param user: The user this should be sent to.
    :param subject: The e-mail subject. Should be localized.
    :param template: The filename of a template to be used. It will
                     be rendered with the recipient's locale. Alternatively, you
                     can pass a LazyI18nString and leave ``context`` empty
    :param context: The context for rendering the template.
    :param event: The event, used for determining the sender of the e-mail

    :return: ``False`` on obvious failures, like the user having to e-mail
    address, ``True`` otherwise. ``True`` does not necessarily mean that
    the email has been sent, just that it has been queued by the e-mail
    backend.
    """
    if not user.email:
        return False

    _lng = translation.get_language()
    translation.activate(user.locale or settings.LANGUAGE_CODE)

    if isinstance(template, LazyI18nString):
        body = str(template)
    else:
        tpl = get_template(template)
        body = tpl.render(context)

    sender = event.settings.get('mail_from') if event else settings.MAIL_FROM

    subject = str(subject)
    prefix = event.settings.get('mail_prefix')
    if prefix:
        subject = "[%s] %s" % (prefix, subject)

    body += "\r\n\r\n----\r\n"
    body += _(
        "You are receiving this e-mail because you placed an order for %s." % event.name
    )
    body += "\r\n"
    body += _(
        "You can view all of your orders at the following URL:"
    )
    body += "\r\n"
    body += build_absolute_uri(
        'presale:event.orders', kwargs={
            'event': event.slug,
            'organizer': event.organizer.slug
        }
    )
    body += "\r\n"

    email = EmailMessage(
        subject, body, sender,
        to=[user.email]
    )

    try:
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Error sending e-mail')
        return False
    finally:
        translation.activate(_lng)
