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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel, Sanket Dasgupta, Sohalt, Tobias Kunze, Tobias
# Kunze, cherti
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import hashlib
import inspect
import logging
import mimetypes
import os
import re
import smtplib
import ssl
import warnings
from email.mime.image import MIMEImage
from email.utils import formataddr
from typing import Any, Dict, List, Sequence, Union
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from celery import chain
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.mail import (
    EmailMultiAlternatives, SafeMIMEMultipart, get_connection,
)
from django.core.mail.message import SafeMIMEText
from django.db import transaction
from django.template.loader import get_template
from django.utils.timezone import now, override
from django.utils.translation import gettext as _, pgettext
from django_scopes import scope, scopes_disabled
from i18nfield.strings import LazyI18nString
from text_unidecode import unidecode

from pretix.base.email import ClassicMailRenderer
from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, Customer, Event, Invoice, InvoiceAddress, Order, OrderPosition,
    Organizer, User,
)
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.services.tickets import get_tickets_for_order
from pretix.base.signals import email_filter, global_email_filter
from pretix.celery_app import app
from pretix.helpers.format import format_map
from pretix.helpers.hierarkey import clean_filename
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.ical import get_private_icals

logger = logging.getLogger('pretix.base.mail')
INVALID_ADDRESS = 'invalid-pretix-mail-address'


class TolerantDict(dict):

    def __missing__(self, key):
        return key


class SendMailException(Exception):
    pass


def clean_sender_name(sender_name: str) -> str:
    # Emails with @ in their sender name are rejected by some mailservers (e.g. Microsoft) because it looks like
    # a phishing attempt.
    sender_name = sender_name.replace("@", " ")

    # Emails with excessively long sender names are rejected by some mailservers
    if len(sender_name) > 75:
        sender_name = sender_name[:75] + "..."

    return sender_name


def mail(email: Union[str, Sequence[str]], subject: str, template: Union[str, LazyI18nString],
         context: Dict[str, Any] = None, event: Event = None, locale: str = None, order: Order = None,
         position: OrderPosition = None, *, headers: dict = None, sender: str = None, organizer: Organizer = None,
         customer: Customer = None, invoices: Sequence = None, attach_tickets=False, auto_email=True, user=None,
         attach_ical=False, attach_cached_files: Sequence = None, attach_other_files: list=None,
         plain_text_only=False, no_order_links=False, cc: Sequence[str]=None, bcc: Sequence[str]=None):
    """
    Sends out an email to a user. The mail will be sent synchronously or asynchronously depending on the installation.

    :param email: The email address of the recipient

    :param subject: The email subject. Should be localized to the recipients's locale or a lazy object that will be
        localized by being casted to a string.

    :param template: The filename of a template to be used. It will be rendered with the locale given in the locale
        argument and the context given in the next argument. Alternatively, you can pass a LazyI18nString and
        ``context`` will be used as the argument to a ``pretix.helpers.format.format_map(template, context)`` call on the template.

    :param context: The context for rendering the template (see ``template`` parameter)

    :param event: The event this email is related to (optional). If set, this will be used to determine the sender,
        a possible prefix for the subject and the SMTP server that should be used to send this email.

    :param organizer: The event this organizer is related to (optional). If set, this will be used to determine the sender,
        a possible prefix for the subject and the SMTP server that should be used to send this email.

    :param order: The order this email is related to (optional). If set, this will be used to include a link to the
        order below the email.

    :param position: The order position this email is related to (optional). If set, this will be used to include a link
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

    :param customer: The customer this email is sent to

    :param attach_cached_files: A list of cached file to attach to this email.

    :param attach_other_files: A list of file paths on our storage to attach.

    :param plain_text_only: If set to ``True``, rendering a HTML version will be skipped.

    :param no_order_links: If set to ``True``, no link to the order confirmation page will be auto-appended. Currently
                           only allowed to use together with ``plain_text_only`` since HTML renderers add their own
                           links.

    :raises MailOrderException: on obvious, immediate failures. Not raising an exception does not necessarily mean
        that the email has been sent, just that it has been queued by the email backend.
    """
    if email == INVALID_ADDRESS:
        return

    if no_order_links and not plain_text_only:
        raise ValueError('If you set no_order_links, you also need to set plain_text_only.')

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
        renderer = ClassicMailRenderer(None, organizer)
        content_plain = body_plain = render_mail(template, context)
        subject = str(subject).format_map(TolerantDict(context))
        sender = (
            sender or
            (event.settings.get('mail_from') if event else None) or
            (organizer.settings.get('mail_from') if organizer else None) or
            settings.MAIL_FROM
        )
        if event:
            sender_name = clean_sender_name(event.settings.mail_from_name or str(event.name))
            sender = formataddr((sender_name, sender))
        elif organizer:
            sender_name = clean_sender_name(organizer.settings.mail_from_name or str(organizer.name))
            sender = formataddr((sender_name, sender))
        else:
            sender = formataddr((clean_sender_name(settings.PRETIX_INSTANCE_NAME), sender))

        subject = raw_subject = str(subject).replace('\n', ' ').replace('\r', '')[:900]
        signature = ""

        bcc = list(bcc or [])

        settings_holder = event or organizer

        if event:
            timezone = event.timezone
        elif user:
            timezone = ZoneInfo(user.timezone)
        elif organizer:
            timezone = organizer.timezone
        else:
            timezone = ZoneInfo(settings.TIME_ZONE)

        if settings_holder:
            if settings_holder.settings.mail_bcc:
                for bcc_mail in settings_holder.settings.mail_bcc.split(','):
                    bcc.append(bcc_mail.strip())

            if settings_holder.settings.mail_from in (settings.DEFAULT_FROM_EMAIL, settings.MAIL_FROM_ORGANIZERS) \
                    and settings_holder.settings.contact_mail and not headers.get('Reply-To'):
                headers['Reply-To'] = settings_holder.settings.contact_mail

            prefix = settings_holder.settings.get('mail_prefix')
            if prefix and prefix.startswith('[') and prefix.endswith(']'):
                prefix = prefix[1:-1]
            if prefix:
                subject = "[%s] %s" % (prefix, subject)

            body_plain += "\r\n\r\n-- \r\n"

            signature = str(settings_holder.settings.get('mail_text_signature'))
            if signature:
                signature = signature.format(event=event.name if event else '')
                body_plain += signature
                body_plain += "\r\n\r\n-- \r\n"

        if event:
            renderer = event.get_html_mail_renderer()

            if order and order.testmode:
                subject = "[TESTMODE] " + subject

            if order and position and not no_order_links:
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
            elif order and not no_order_links:
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

        with override(timezone):
            try:
                if plain_text_only:
                    body_html = None
                elif 'position' in inspect.signature(renderer.render).parameters:
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
            to=[email] if isinstance(email, str) else list(email),
            cc=cc,
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
            user=user.pk if user else None,
            organizer=organizer.pk if organizer else None,
            customer=customer.pk if customer else None,
            attach_cached_files=[(cf.id if isinstance(cf, CachedFile) else cf) for cf in attach_cached_files] if attach_cached_files else [],
            attach_other_files=attach_other_files,
        )

        if invoices:
            task_chain = [invoice_pdf_task.si(i.pk).on_error(send_task) for i in invoices if not i.file]
        else:
            task_chain = []

        task_chain.append(send_task)

        if 'locmem' in settings.EMAIL_BACKEND:
            # This clause is triggered during unit tests, because transaction.on_commit never fires due to the nature
            # Django's unit tests work
            chain(*task_chain).apply_async()
        else:
            transaction.on_commit(
                lambda: chain(*task_chain).apply_async()
            )


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


@app.task(base=TransactionAwareTask, bind=True, acks_late=True)
def mail_send_task(self, *args, to: List[str], subject: str, body: str, html: str, sender: str,
                   event: int = None, position: int = None, headers: dict = None, cc: List[str] = None, bcc: List[str] = None,
                   invoices: List[int] = None, order: int = None, attach_tickets=False, user=None,
                   organizer=None, customer=None, attach_ical=False, attach_cached_files: List[int] = None,
                   attach_other_files: List[str] = None) -> bool:
    email = CustomEmail(subject, body, sender, to=to, cc=cc, bcc=bcc, headers=headers)
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
    elif organizer:
        with scopes_disabled():
            organizer = Organizer.objects.get(id=organizer)
        backend = organizer.get_mail_backend()
        cm = lambda: scope(organizer=organizer)  # noqa
    else:
        backend = get_connection(fail_silently=False)
        cm = lambda: scopes_disabled()  # noqa

    with cm():
        if customer:
            customer = Customer.objects.get(pk=customer)
        log_target = user or customer

        if event:
            if order:
                try:
                    order = event.orders.get(pk=order)
                    log_target = order
                except Order.DoesNotExist:
                    order = None
                else:
                    with language(order.locale, event.settings.region):
                        if not event.settings.mail_attach_tickets:
                            attach_tickets = False
                        if position:
                            try:
                                position = order.positions.get(pk=position)
                            except OrderPosition.DoesNotExist:
                                attach_tickets = False
                        if attach_tickets:
                            args = []
                            attach_size = 0
                            for name, ct in get_tickets_for_order(order, base_position=position):
                                try:
                                    content = ct.file.read()
                                    args.append((name, content, ct.type))
                                    attach_size += len(content)
                                except:
                                    # This sometimes fails e.g. with FileNotFoundError. We haven't been able to figure out
                                    # why (probably some race condition with ticket cache invalidation?), so retry later.
                                    try:
                                        self.retry(max_retries=5, countdown=60)
                                    except MaxRetriesExceededError:
                                        # Well then, something is really wrong, let's send it without attachment before we
                                        # don't sent at all
                                        logger.exception('Could not attach invoice to email')
                                        pass

                            if attach_size < settings.FILE_UPLOAD_MAX_SIZE_EMAIL_ATTACHMENT - 1:
                                # Do not attach more than (limit - 1 MB) in tickets (1MB space for invoice, email itself, …),
                                # it will bounce way to often.
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
                            fname = re.sub('[^a-zA-Z0-9 ]', '-', unidecode(pgettext('attachment_filename', 'Calendar invite')))
                            for i, cal in enumerate(get_private_icals(event, [position] if position else order.positions.all())):
                                email.attach('{}{}.ics'.format(fname, f'-{i + 1}' if i > 0 else ''), cal.serialize(), 'text/calendar')

            email = email_filter.send_chained(event, 'message', message=email, order=order, user=user)

        invoices_sent = []
        if invoices:
            invoices = Invoice.objects.filter(pk__in=invoices)
            for inv in invoices:
                if inv.file:
                    try:
                        # We try to give the invoice a more human-readable name, e.g. "Invoice_ABC-123.pdf" instead of
                        # just "ABC-123.pdf", but we only do so if our currently selected language allows to do this
                        # as ASCII text. For example, we would not want a "فاتورة_" prefix for our filename since this
                        # has shown to cause deliverability problems of the email and deliverability wins.
                        filename = pgettext('invoice', 'Invoice {num}').format(num=inv.number).replace(' ', '_') + '.pdf'
                        if not re.match("^[a-zA-Z0-9-_%./,&:# ]+$", filename):
                            filename = inv.number.replace(' ', '_') + '.pdf'
                        filename = re.sub("[^a-zA-Z0-9-_.]+", "_", filename)
                        with language(inv.order.locale):
                            email.attach(
                                filename,
                                inv.file.file.read(),
                                'application/pdf'
                            )
                        invoices_sent.append(inv)
                    except:
                        logger.exception('Could not attach invoice to email')
                        pass

        if attach_other_files:
            for fname in attach_other_files:
                ftype, _ = mimetypes.guess_type(fname)
                data = default_storage.open(fname).read()
                try:
                    email.attach(
                        clean_filename(os.path.basename(fname)),
                        data,
                        ftype
                    )
                except:
                    logger.exception('Could not attach file to email')
                    pass

        if attach_cached_files:
            for cf in CachedFile.objects.filter(id__in=attach_cached_files):
                if cf.file:
                    try:
                        email.attach(
                            cf.filename,
                            cf.file.file.read(),
                            cf.type,
                        )
                    except:
                        logger.exception('Could not attach file to email')
                        pass

        email = global_email_filter.send_chained(event, 'message', message=email, user=user, order=order,
                                                 organizer=organizer, customer=customer)

        try:
            backend.send_messages([email])
        except (smtplib.SMTPResponseException, smtplib.SMTPSenderRefused) as e:
            if e.smtp_code in (101, 111, 421, 422, 431, 432, 442, 447, 452):
                if e.smtp_code == 432 and settings.HAS_REDIS:
                    # This is likely Microsoft Exchange Online which has a pretty bad rate limit of max. 3 concurrent
                    # SMTP connections which is *easily* exceeded with many celery threads. Just retrying with exponential
                    # backoff won't be good enough if we have a lot of emails, instead we'll need to make sure our retry
                    # intervals scatter such that the email won't all be retried at the same time again and cause the
                    # same problem.
                    # See also https://docs.microsoft.com/en-us/exchange/troubleshoot/send-emails/smtp-submission-improvements
                    from django_redis import get_redis_connection

                    redis_key = "pretix_mail_retry_" + hashlib.sha1(f"{getattr(backend, 'username', '_')}@{getattr(backend, 'host', '_')}".encode()).hexdigest()
                    rc = get_redis_connection("redis")
                    cnt = rc.incr(redis_key)
                    rc.expire(redis_key, 300)

                    max_retries = 10
                    retry_after = min(30 + cnt * 10, 1800)
                else:
                    # Most likely some other kind of temporary failure, retry again (but pretty soon)
                    max_retries = 5
                    retry_after = [10, 30, 60, 300, 900, 900][self.request.retries]

                try:
                    self.retry(max_retries=max_retries, countdown=retry_after)
                except MaxRetriesExceededError:
                    if log_target:
                        log_target.log_action(
                            'pretix.email.error',
                            data={
                                'subject': 'SMTP code {}, max retries exceeded'.format(e.smtp_code),
                                'message': e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error),
                                'recipient': '',
                                'invoices': [],
                            }
                        )
                    raise e

            logger.exception('Error sending email')
            if log_target:
                log_target.log_action(
                    'pretix.email.error',
                    data={
                        'subject': 'SMTP code {}'.format(e.smtp_code),
                        'message': e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error),
                        'recipient': '',
                        'invoices': [],
                    }
                )

            raise SendMailException('Failed to send an email to {}.'.format(to))
        except smtplib.SMTPRecipientsRefused as e:
            smtp_codes = [a[0] for a in e.recipients.values()]

            if not any(c >= 500 for c in smtp_codes):
                # Not a permanent failure (mailbox full, service unavailable), retry later, but with large intervals
                try:
                    self.retry(max_retries=5, countdown=[60, 300, 600, 1200, 1800, 1800][self.request.retries])
                except MaxRetriesExceededError:
                    # ignore and go on with logging the error
                    pass

            logger.exception('Error sending email')
            if log_target:
                message = []
                for e, val in e.recipients.items():
                    message.append(f'{e}: {val[0]} {val[1].decode()}')

                log_target.log_action(
                    'pretix.email.error',
                    data={
                        'subject': 'SMTP error',
                        'message': '\n'.join(message),
                        'recipient': '',
                        'invoices': [],
                    }
                )

            raise SendMailException('Failed to send an email to {}.'.format(to))
        except Exception as e:
            if isinstance(e, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ssl.SSLError, OSError)):
                try:
                    self.retry(max_retries=5, countdown=[10, 30, 60, 300, 900, 900][self.request.retries])
                except MaxRetriesExceededError:
                    if log_target:
                        log_target.log_action(
                            'pretix.email.error',
                            data={
                                'subject': 'Internal error',
                                'message': 'Max retries exceeded',
                                'recipient': '',
                                'invoices': [],
                            }
                        )
                    raise e
            if log_target:
                log_target.log_action(
                    'pretix.email.error',
                    data={
                        'subject': 'Internal error',
                        'message': str(e),
                        'recipient': '',
                        'invoices': [],
                    }
                )
            logger.exception('Error sending email')
            raise SendMailException('Failed to send an email to {}.'.format(to))
        else:
            for i in invoices_sent:
                i.sent_to_customer = now()
                i.save(update_fields=['sent_to_customer'])


def mail_send(*args, **kwargs):
    mail_send_task.apply_async(args=args, kwargs=kwargs)


def render_mail(template, context):
    if isinstance(template, LazyI18nString):
        body = str(template)
        if context:
            body = format_map(body, context)
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

        return str(email), cid_images
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
    image_src = image_src.strip()
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
            image_type = os.path.splitext(path)[1][1:]

            response = requests.get(image_src, verify=verify_ssl)
            mime_image = MIMEImage(
                response.content, _subtype=image_type)

        mime_image.add_header('Content-ID', '<%s>' % cid_id)
        mime_image.add_header('Content-Disposition', 'inline;\n filename="{}.{}"'.format(cid_id, image_type))

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
