import logging
import smtplib
from email.utils import formataddr
from typing import Any, Dict, List, Union

import cssutils
from celery import chain
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import get_template
from django.utils.translation import ugettext as _
from i18nfield.strings import LazyI18nString

from pretix.base.email import ClassicMailRenderer
from pretix.base.i18n import language
from pretix.base.models import Event, Invoice, InvoiceAddress, Order
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.services.tickets import get_tickets_for_order
from pretix.base.signals import email_filter
from pretix.celery_app import app
from pretix.multidomain.urlreverse import build_absolute_uri

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
         order: Order=None, headers: dict=None, sender: str=None, invoices: list=None,
         attach_tickets=False):
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

    :param headers: A dict of custom mail headers to add to the mail

    :param locale: The locale to be used while evaluating the subject and the template

    :param sender: Set the sender email address. If not set and ``event`` is set, the event's default will be used,
        otherwise the system default.

    :param invoices: A list of invoices to attach to this email.

    :param attach_tickets: Whether to attach tickets to this email, if they are available to download.

    :raises MailOrderException: on obvious, immediate failures. Not raising an exception does not necessarily mean
        that the email has been sent, just that it has been queued by the email backend.
    """
    if email == INVALID_ADDRESS:
        return

    headers = headers or {}

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
        subject = str(subject).format_map(context)
        sender = sender or (event.settings.get('mail_from') if event else settings.MAIL_FROM)
        if event:
            sender = formataddr((str(event.name), sender))
        else:
            sender = formataddr((settings.PRETIX_INSTANCE_NAME, sender))

        subject = str(subject)
        signature = ""

        bcc = []
        if event:
            renderer = event.get_html_mail_renderer()
            if event.settings.mail_bcc:
                bcc.append(event.settings.mail_bcc)

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

            if order:
                if order.testmode:
                    subject = "[TESTMODE] " + subject
                body_plain += _(
                    "You are receiving this email because you placed an order for {event}."
                ).format(event=event.name)
                body_plain += "\r\n"
                body_plain += _(
                    "You can view your order details at the following URL:\n{orderurl}."
                ).replace("\n", "\r\n").format(
                    event=event.name, orderurl=build_absolute_uri(
                        order.event, 'presale:event.order', kwargs={
                            'order': order.code,
                            'secret': order.secret
                        }
                    )
                )
            body_plain += "\r\n"

        try:
            body_html = renderer.render(content_plain, signature, str(subject), order)
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
            invoices=[i.pk for i in invoices] if invoices else [],
            order=order.pk if order else None,
            attach_tickets=attach_tickets
        )

        if invoices:
            task_chain = [invoice_pdf_task.si(i.pk).on_error(send_task) for i in invoices if not i.file]
        else:
            task_chain = []

        task_chain.append(send_task)
        chain(*task_chain).apply_async()


@app.task(bind=True)
def mail_send_task(self, *args, to: List[str], subject: str, body: str, html: str, sender: str,
                   event: int=None, headers: dict=None, bcc: List[str]=None, invoices: List[int]=None,
                   order: int=None, attach_tickets=False) -> bool:
    email = EmailMultiAlternatives(subject, body, sender, to=to, bcc=bcc, headers=headers)
    if html is not None:
        email.attach_alternative(html, "text/html")
    if invoices:
        invoices = Invoice.objects.filter(pk__in=invoices)
        for inv in invoices:
            if inv.file:
                try:
                    email.attach(
                        '{}.pdf'.format(inv.number),
                        inv.file.file.read(),
                        'application/pdf'
                    )
                except:
                    logger.exception('Could not attach invoice to email')
                    pass

    if event:
        event = Event.objects.get(id=event)
        backend = event.get_mail_backend()
    else:
        backend = get_connection(fail_silently=False)

    if event:
        if order:
            try:
                order = event.orders.get(pk=order)
            except Order.DoesNotExist:
                order = None
            else:
                if attach_tickets:
                    args = []
                    attach_size = 0
                    for name, ct in get_tickets_for_order(order):
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
                            'pretix.event.order.email.error',
                            data={
                                'subject': 'Attachments skipped',
                                'message': 'Attachment have not been send because {} bytes are likely too large to arrive.'.format(attach_size),
                                'recipient': '',
                                'invoices': [],
                            }
                        )

        email = email_filter.send_chained(event, 'message', message=email, order=order)

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
