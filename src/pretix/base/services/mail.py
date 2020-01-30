import inspect
import logging
import os
import re
import smtplib
import ssl
import warnings
from email.mime.image import MIMEImage
from email.utils import formataddr
from typing import Any, Dict, List, Union
from urllib.parse import urljoin, urlparse

import cssutils
import requests
from bs4 import BeautifulSoup
from celery import chain
from django.conf import settings
from django.core.mail import (
    EmailMultiAlternatives, SafeMIMEMultipart, get_connection,
)
from django.core.mail.message import SafeMIMEText
from django.template.loader import get_template
from django.utils.translation import gettext as _, pgettext
from django_scopes import scope, scopes_disabled
from i18nfield.strings import LazyI18nString

from pretix.base.email import ClassicMailRenderer
from pretix.base.i18n import language
from pretix.base.models import (
    Event, Invoice, InvoiceAddress, Order, OrderPosition, User,
)
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.services.tickets import get_tickets_for_order
from pretix.base.signals import email_filter, global_email_filter
from pretix.celery_app import app
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.ical import get_ical

logger = logging.getLogger('pretix.base.mail')
INVALID_ADDRESS = 'invalid-pretix-mail-address'
cssutils.log.setLevel(logging.CRITICAL)


class TolerantDict(dict):

    def __missing__(self, key):
        return key


class SendMailException(Exception):
    pass


def mail(email: str, subject: str, template: Union[str, LazyI18nString],
         context: Dict[str, Any]=None, event: Event=None, locale: str=None,
         order: Order=None, position: OrderPosition=None, headers: dict=None, sender: str=None,
         invoices: list=None, attach_tickets=False, auto_email=True, user=None, attach_ical=False):
    """
    Sends out an email to a user. The mail will be sent synchronously or asynchronously depending on the installation.

    :param email: The email address of the recipient

    :param subject: The email subject. Should be localized to the recipients's locale or a lazy object that will be
        localized by being casted to a string.

    :param template: The filename of a template to be used. It will be rendered with the locale given in the locale
        argument and the context given in the next argument. Alternatively, you can pass a LazyI18nString and
        ``context`` will be used as the argument to a  Python ``.format_map()`` call on the template.

    :param context: The context for rendering the template (see ``template`` parameter)

    :param event: The event this email is related to (optional). If set, this will be used to determine the sender,
        a possible prefix for the subject and the SMTP server that should be used to send this email.

    :param order: The order this email is related to (optional). If set, this will be used to include a link to the
        order below the email.

    :param order: The order position this email is related to (optional). If set, this will be used to include a link
        to the order position instead of the order below the email.

    :param headers: A dict of custom mail headers to add to the mail

    :param locale: The locale to be used while evaluating the subject and the template

    :param sender: Set the sender email address. If not set and ``event`` is set, the event's default will be used,
        otherwise the system default.

    :param invoices: A list of invoices to attach to this email.

    :param attach_tickets: Whether to attach tickets to this email, if they are available to download.

    :param attach_ical: Whether to attach relevant ``.ics`` files to this email

    :param auto_email: Whether this email is auto-generated

    :param user: The user this email is sent to

    :raises MailOrderException: on obvious, immediate failures. Not raising an exception does not necessarily mean
        that the email has been sent, just that it has been queued by the email backend.
    """
    if email == INVALID_ADDRESS:
        return

    headers = headers or {}
    if auto_email:
        headers['X-Auto-Response-Suppress'] = 'OOF, NRN, AutoReply, RN'
        headers['Auto-Submitted'] = 'auto-generated'

    with language(locale):
        if isinstance(context, dict) and event:
            for k, v in event.meta_data.items():
                context['meta_' + k] = v

        if isinstance(context, dict) and order:
            try:
                context.update({
                    'invoice_name': order.invoice_address.name,
                    'invoice_company': order.invoice_address.company
                })
            except InvoiceAddress.DoesNotExist:
                context.update({
                    'invoice_name': '',
                    'invoice_company': ''
                })
        renderer = ClassicMailRenderer(None)
        content_plain = body_plain = render_mail(template, context)
        subject = str(subject).format_map(TolerantDict(context))
        sender = sender or (event.settings.get('mail_from') if event else settings.MAIL_FROM) or settings.MAIL_FROM
        if event:
            sender_name = event.settings.mail_from_name or str(event.name)
            sender = formataddr((sender_name, sender))
        else:
            sender = formataddr((settings.PRETIX_INSTANCE_NAME, sender))

        subject = raw_subject = str(subject)
        signature = ""

        bcc = []
        if event:
            renderer = event.get_html_mail_renderer()
            if event.settings.mail_bcc:
                for bcc_mail in event.settings.mail_bcc.split(','):
                    bcc.append(bcc_mail.strip())

            if event.settings.mail_from == settings.DEFAULT_FROM_EMAIL and event.settings.contact_mail and not headers.get('Reply-To'):
                headers['Reply-To'] = event.settings.contact_mail

            prefix = event.settings.get('mail_prefix')
            if prefix and prefix.startswith('[') and prefix.endswith(']'):
                prefix = prefix[1:-1]
            if prefix:
                subject = "[%s] %s" % (prefix, subject)

            body_plain += "\r\n\r\n-- \r\n"

            signature = str(event.settings.get('mail_text_signature'))
            if signature:
                signature = signature.format(event=event.name)
                body_plain += signature
                body_plain += "\r\n\r\n-- \r\n"

            if order and order.testmode:
                subject = "[TESTMODE] " + subject

            if order and position:
                body_plain += _(
                    "You are receiving this email because someone placed an order for {event} for you."
                ).format(event=event.name)
                body_plain += "\r\n"
                body_plain += _(
                    "You can view your order details at the following URL:\n{orderurl}."
                ).replace("\n", "\r\n").format(
                    event=event.name, orderurl=build_absolute_uri(
                        order.event, 'presale:event.order.position', kwargs={
                            'order': order.code,
                            'secret': position.web_secret,
                            'position': position.positionid,
                        }
                    )
                )
            elif order:
                body_plain += _(
                    "You are receiving this email because you placed an order for {event}."
                ).format(event=event.name)
                body_plain += "\r\n"
                body_plain += _(
                    "You can view your order details at the following URL:\n{orderurl}."
                ).replace("\n", "\r\n").format(
                    event=event.name, orderurl=build_absolute_uri(
                        order.event, 'presale:event.order.open', kwargs={
                            'order': order.code,
                            'secret': order.secret,
                            'hash': order.email_confirm_hash()
                        }
                    )
                )
            body_plain += "\r\n"

        try:
            if 'position' in inspect.signature(renderer.render).parameters:
                body_html = renderer.render(content_plain, signature, raw_subject, order, position)
            else:
                # Backwards compatibility
                warnings.warn('E-mail renderer called without position argument because position argument is not '
                              'supported.',
                              DeprecationWarning)
                body_html = renderer.render(content_plain, signature, raw_subject, order)
        except:
            logger.exception('Could not render HTML body')
            body_html = None

        send_task = mail_send_task.si(
            to=[email],
            bcc=bcc,
            subject=subject,
            body=body_plain,
            html=body_html,
            sender=sender,
            event=event.id if event else None,
            headers=headers,
            invoices=[i.pk for i in invoices] if invoices and not position else [],
            order=order.pk if order else None,
            position=position.pk if position else None,
            attach_tickets=attach_tickets,
            attach_ical=attach_ical,
            user=user.pk if user else None
        )

        if invoices:
            task_chain = [invoice_pdf_task.si(i.pk).on_error(send_task) for i in invoices if not i.file]
        else:
            task_chain = []

        task_chain.append(send_task)
        chain(*task_chain).apply_async()


class CustomEmail(EmailMultiAlternatives):
    def _create_mime_attachment(self, content, mimetype):
        """
        Convert the content, mimetype pair into a MIME attachment object.

        If the mimetype is message/rfc822, content may be an
        email.Message or EmailMessage object, as well as a str.
        """
        basetype, subtype = mimetype.split('/', 1)
        if basetype == 'multipart' and isinstance(content, SafeMIMEMultipart):
            return content
        return super()._create_mime_attachment(content, mimetype)


@app.task(base=TransactionAwareTask, bind=True)
def mail_send_task(self, *args, to: List[str], subject: str, body: str, html: str, sender: str,
                   event: int=None, position: int=None, headers: dict=None, bcc: List[str]=None,
                   invoices: List[int]=None, order: int=None, attach_tickets=False, user=None,
                   attach_ical=False) -> bool:
    email = CustomEmail(subject, body, sender, to=to, bcc=bcc, headers=headers)
    if html is not None:
        html_message = SafeMIMEMultipart(_subtype='related', encoding=settings.DEFAULT_CHARSET)
        html_with_cid, cid_images = replace_images_with_cid_paths(html)
        html_message.attach(SafeMIMEText(html_with_cid, 'html', settings.DEFAULT_CHARSET))
        attach_cid_images(html_message, cid_images, verify_ssl=True)
        email.attach_alternative(html_message, "multipart/related")

    if user:
        user = User.objects.get(pk=user)

    if event:
        with scopes_disabled():
            event = Event.objects.get(id=event)
        backend = event.get_mail_backend()
        cm = lambda: scope(organizer=event.organizer)  # noqa
    else:
        backend = get_connection(fail_silently=False)
        cm = lambda: scopes_disabled()  # noqa

    with cm():
        if invoices:
            invoices = Invoice.objects.filter(pk__in=invoices)
            for inv in invoices:
                if inv.file:
                    try:
                        with language(inv.order.locale):
                            email.attach(
                                pgettext('invoice', 'Invoice {num}').format(num=inv.number).replace(' ', '_') + '.pdf',
                                inv.file.file.read(),
                                'application/pdf'
                            )
                    except:
                        logger.exception('Could not attach invoice to email')
                        pass
        if event:
            if order:
                try:
                    order = event.orders.get(pk=order)
                except Order.DoesNotExist:
                    order = None
                else:
                    if position:
                        try:
                            position = order.positions.get(pk=position)
                        except OrderPosition.DoesNotExist:
                            attach_tickets = False
                    if attach_tickets:
                        args = []
                        attach_size = 0
                        for name, ct in get_tickets_for_order(order, base_position=position):
                            content = ct.file.read()
                            args.append((name, content, ct.type))
                            attach_size += len(content)

                        if attach_size < 4 * 1024 * 1024:
                            # Do not attach more than 4MB, it will bounce way to often.
                            for a in args:
                                try:
                                    email.attach(*a)
                                except:
                                    pass
                        else:
                            order.log_action(
                                'pretix.event.order.email.attachments.skipped',
                                data={
                                    'subject': 'Attachments skipped',
                                    'message': 'Attachment have not been send because {} bytes are likely too large to arrive.'.format(attach_size),
                                    'recipient': '',
                                    'invoices': [],
                                }
                            )
                    if attach_ical:
                        ical_events = set()
                        if event.has_subevents:
                            if position:
                                ical_events.add(position.subevent)
                            else:
                                for p in order.positions.all():
                                    ical_events.add(p.subevent)
                        else:
                            ical_events.add(order.event)

                        for i, e in enumerate(ical_events):
                            cal = get_ical([e])
                            email.attach('event-{}.ics'.format(i), cal.serialize(), 'text/calendar')

            email = email_filter.send_chained(event, 'message', message=email, order=order, user=user)

        email = global_email_filter.send_chained(event, 'message', message=email, user=user, order=order)

        try:
            backend.send_messages([email])
        except smtplib.SMTPResponseException as e:
            if e.smtp_code in (101, 111, 421, 422, 431, 442, 447, 452):
                self.retry(max_retries=5, countdown=2 ** (self.request.retries * 2))
            logger.exception('Error sending email')

            if order:
                order.log_action(
                    'pretix.event.order.email.error',
                    data={
                        'subject': 'SMTP code {}'.format(e.smtp_code),
                        'message': e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error),
                        'recipient': '',
                        'invoices': [],
                    }
                )

            raise SendMailException('Failed to send an email to {}.'.format(to))
        except Exception as e:
            if isinstance(e, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ssl.SSLError, OSError)):
                self.retry(max_retries=5, countdown=2 ** (self.request.retries * 2))
            if order:
                order.log_action(
                    'pretix.event.order.email.error',
                    data={
                        'subject': 'Internal error',
                        'message': str(e),
                        'recipient': '',
                        'invoices': [],
                    }
                )
            logger.exception('Error sending email')
            raise SendMailException('Failed to send an email to {}.'.format(to))


def mail_send(*args, **kwargs):
    mail_send_task.apply_async(args=args, kwargs=kwargs)


def render_mail(template, context):
    if isinstance(template, LazyI18nString):
        body = str(template)
        if context:
            body = body.format_map(TolerantDict(context))
    else:
        tpl = get_template(template)
        body = tpl.render(context)
    return body


def replace_images_with_cid_paths(body_html):
    if body_html:
        email = BeautifulSoup(body_html, "lxml")
        cid_images = []
        for image in email.findAll('img'):
            original_image_src = image['src']

            try:
                cid_id = "image_%s" % cid_images.index(original_image_src)
            except ValueError:
                cid_images.append(original_image_src)
                cid_id = "image_%s" % (len(cid_images) - 1)

            image['src'] = "cid:%s" % cid_id

        return email.prettify(), cid_images
    else:
        return body_html, []


def attach_cid_images(msg, cid_images, verify_ssl=True):
    if cid_images and len(cid_images) > 0:

        msg.mixed_subtype = 'mixed'
        for key, image in enumerate(cid_images):
            cid = 'image_%s' % key
            try:
                mime_image = convert_image_to_cid(
                    image, cid, verify_ssl)
                if mime_image:
                    msg.attach(mime_image)
            except:
                logger.exception("ERROR attaching CID image %s[%s]" % (cid, image))


def encoder_linelength(msg):
    """
    RFC1341 mandates that base64 encoded data may not be longer than 76 characters per line
    https://www.w3.org/Protocols/rfc1341/5_Content-Transfer-Encoding.html section 5.2
    """

    orig = msg.get_payload(decode=True).replace(b"\n", b"").replace(b"\r", b"")
    max_length = 76
    pieces = []
    for i in range(0, len(orig), max_length):
        chunk = orig[i:i + max_length]
        pieces.append(chunk)
    msg.set_payload(b"\r\n".join(pieces))


def convert_image_to_cid(image_src, cid_id, verify_ssl=True):
    try:
        if image_src.startswith('data:image/'):
            image_type, image_content = image_src.split(',', 1)
            image_type = re.findall(r'data:image/(\w+);base64', image_type)[0]
            mime_image = MIMEImage(image_content, _subtype=image_type, _encoder=encoder_linelength)
            mime_image.add_header('Content-Transfer-Encoding', 'base64')
        elif image_src.startswith('data:'):
            logger.exception("ERROR creating MIME element %s[%s]" % (cid_id, image_src))
            return None
        else:
            image_src = normalize_image_url(image_src)

            path = urlparse(image_src).path
            guess_subtype = os.path.splitext(path)[1][1:]

            response = requests.get(image_src, verify=verify_ssl)
            mime_image = MIMEImage(
                response.content, _subtype=guess_subtype)

        mime_image.add_header('Content-ID', '<%s>' % cid_id)

        return mime_image
    except:
        logger.exception("ERROR creating mime_image %s[%s]" % (cid_id, image_src))
        return None


def normalize_image_url(url):
    if '://' not in url:
        """
        If we see a relative URL in an email, we can't know if it is meant to be a media file
        or a static file, so we need to guess. If it is a static file included with the
        ``{% static %}`` template tag (as it should be), then ``STATIC_URL`` is already prepended.
        If ``STATIC_URL`` is absolute, then ``url`` should already be absolute and this
        function should not be triggered. Thus, if we see a relative URL and ``STATIC_URL``
        is absolute *or* ``url`` does not start with ``STATIC_URL``, we can be sure this
        is a media file (or a programmer error …).

        Constructing the URL of either a static file or a media file from settings is still
        not clean, since custom storage backends might very well use more complex approaches
        to build those URLs. However, this is good enough as a best-effort approach. Complex
        storage backends (such as cloud storages) will return absolute URLs anyways so this
        function is not needed in that case.
        """
        if '://' not in settings.STATIC_URL and url.startswith(settings.STATIC_URL):
            url = urljoin(settings.SITE_URL, url)
        else:
            url = urljoin(settings.MEDIA_URL, url)
    return url
