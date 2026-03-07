#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import math
import mimetypes
import os
import random
import re
import smtplib
import time
import uuid
import warnings
from datetime import timedelta, datetime
from email.mime.image import MIMEImage
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Sequence, Union
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from celery import chain
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.mail import EmailMultiAlternatives, SafeMIMEMultipart
from django.core.mail.message import SafeMIMEText
from django.db import connection, transaction
from django.db.models import Q
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.html import escape
from django.utils.timezone import now, override
from django.utils.translation import gettext as _, pgettext
from django_redis import get_redis_connection
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString
from text_unidecode import unidecode

from pretix.base.email import ClassicMailRenderer
from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, Customer, Event, Invoice, InvoiceAddress, Order, OrderPosition,
    Organizer, User,
)
from pretix.base.models.mail import OutgoingMail
from pretix.base.services.invoices import invoice_pdf_task
from pretix.base.services.tasks import TransactionAwareTask
from pretix.base.services.tickets import get_tickets_for_order
from pretix.base.signals import (
    email_filter, global_email_filter, periodic_task,
)
from pretix.celery_app import app
from pretix.helpers import OF_SELF
from pretix.helpers.format import (
    FormattedString, PlainHtmlAlternativeString, SafeFormatter, format_map,
)
from pretix.helpers.hierarkey import clean_filename
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.ical import get_private_icals

logger = logging.getLogger('pretix.base.mail')
INVALID_ADDRESS = 'invalid-pretix-mail-address'


class TolerantDict(dict):

    def __missing__(self, key):
        return key


class SendMailException(Exception):
    """
    Deprecated, not thrown any more.
    """
    pass


class WithholdMailException(Exception):
    def __init__(self, error, error_detail):
        self.error = error
        self.error_detail = error_detail


class MailRateLimitException(Exception):
    """
    Raised when no rate-limit token is available. The task will be retried.
    """
    pass


def parse_rate_limit(rate_limit_str: str) -> tuple[int, int]:
    """
    Parse rate limit format like '10/s' or '600/m' into (count, interval_seconds).

    :param rate_limit_str: Format like '10/s' (per second), '600/m' (per minute), '3600/h' (per hour)
    :return: Tuple of (count, interval_seconds)
    :raises ValueError: If format is invalid

    Examples:
        '10/s' -> (10, 1)
        '600/m' -> (600, 60)
        '3600/h' -> (3600, 3600)
    """
    if not rate_limit_str or '/' not in rate_limit_str:
        raise ValueError(f"Invalid rate limit format: {rate_limit_str}. Expected format like '10/s', '600/m', or '3600/h'")

    try:
        count_str, interval_str = rate_limit_str.strip().split('/')
        count = int(count_str)

        interval_map = {
            's': 1,
            'm': 60,
            'h': 3600,
        }

        interval_unit = interval_str.strip().lower()
        if interval_unit not in interval_map:
            raise ValueError(f"Unknown interval unit: {interval_unit}. Expected 's', 'm', or 'h'")

        interval_seconds = interval_map[interval_unit]
        return (count, interval_seconds)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid rate limit format: {rate_limit_str}. Expected format like '10/s', '600/m', or '3600/h'") from e


def get_mail_rate_limit_config() -> tuple[int, int] | None:
    """
    Get the configured mail rate limit from settings.

    :return: Tuple of (count, interval_seconds) or None if not configured or Redis unavailable
    """
    rate_limit_str = getattr(settings, 'MAIL_RATE_LIMIT', None)
    if not rate_limit_str:
        return None

    # Graceful degradation: if Redis is not available, log warning and skip rate limiting
    if not settings.HAS_REDIS:
        logger.warning('MAIL_RATE_LIMIT configured but Redis is not available. Rate limiting will be skipped.')
        return None

    try:
        return parse_rate_limit(rate_limit_str)
    except ValueError as e:
        logger.error(f'Failed to parse MAIL_RATE_LIMIT setting: {e}')
        return None


def try_acquire_mail_token() -> bool:
    """
    Try to acquire a rate-limit token for sending an email.

    This implements the Token Bucket pattern for rate limiting. It maintains a Redis counter
    and checks if tokens are available based on elapsed time since the last reset.
    Time handling is aligned to calendar boundaries (second/minute/hour) to provide
    deterministic and predictable rate-limit windows.

    :return: True if token acquired
    :raises MailRateLimitException: If rate limit exceeded (caller should retry the task)
    """
    rate_config = get_mail_rate_limit_config()
    if not rate_config:
        # No rate limiting configured or Redis unavailable
        return True

    count, interval_seconds = rate_config

    try:
        rc = get_redis_connection("redis")

        # Use a Redis key to track the token bucket
        bucket_key = 'mail_rate_limit:bucket'
        last_refill_key = 'mail_rate_limit:last_refill'

        # Calendar-aligned rounding to the configured rate-limit unit.
        now_dt = datetime.fromtimestamp(time.time())

        if interval_seconds == 1:  # per second: round to full seconds
            now_dt = now_dt.replace(microsecond=0)
        elif interval_seconds == 60:  # per minute: round to full minutes
            now_dt = now_dt.replace(second=0, microsecond=0)
        elif interval_seconds == 3600:  # per hour: round to full hours
            now_dt = now_dt.replace(minute=0, second=0, microsecond=0)

        now = now_dt.timestamp()

        current_tokens_raw = rc.get(bucket_key)
        last_refill_raw = rc.get(last_refill_key)

        if current_tokens_raw is None:
            current_tokens = count
        else:
            current_tokens = int(current_tokens_raw)

        if last_refill_raw is None:
            last_refill = now
        else:
            last_refill = float(last_refill_raw)

        # Calculate tokens to add based on elapsed time
        elapsed = now - last_refill

        # Calculate how many tokens to regenerate
        # Rate: count tokens per interval_seconds
        # So in 'elapsed' seconds we regenerate (count / interval_seconds) * elapsed tokens
        tokens_to_add = int((count / interval_seconds) * elapsed)

        if tokens_to_add > 0:
            current_tokens = min(count, current_tokens + tokens_to_add)
            # Advance refill timestamp only by the consumed refill interval to avoid drift.
            refill_step = interval_seconds / count
            last_refill = last_refill + (tokens_to_add * refill_step)

        # Try to consume one token
        if current_tokens > 0:
            current_tokens -= 1
            rc.set(bucket_key, current_tokens, ex=interval_seconds * 2)
            rc.set(last_refill_key, last_refill, ex=interval_seconds * 2)
            logger.info(f'Mail rate-limit token acquired. Remaining: {current_tokens}/{count}')
            return True
        else:
            rc.set(last_refill_key, last_refill, ex=interval_seconds * 2)
            # Calculate how long to wait until next token is available
            time_until_next = interval_seconds / count
            logger.info(f'Mail rate-limit exceeded. Rate: {count}/{interval_seconds}s. Next token in ~{time_until_next:.2f}s')
            raise MailRateLimitException(f'Rate limit exceeded: {count} mails per {interval_seconds}s')

    except MailRateLimitException:
        raise
    except Exception as e:
        logger.exception(f'Error acquiring mail rate-limit token: {e}')
        # On unexpected errors, allow mail to be sent (graceful degradation)
        return True


def get_rate_limit_retry_countdown(pending_count: int) -> int:
    """
    Calculate retry countdown for a rate-limited mail.

    Retries are distributed across upcoming calendar-aligned windows using jitter.
    The distribution is intentionally compressed to keep total delay practical,
    accepting that some mails may need additional retries.
    """

    rate_config = get_mail_rate_limit_config()
    if not rate_config:
        logger.error('Rate limit exceeded but no rate limit config available. THIS SHOULD NOT HAPPEN. Defaulting to fixed retry time.')
        return random.uniform(10, 90)  # Fallback: random retry between 10 and 90 seconds

    count, interval_seconds = rate_config
    effective_pending = max(1, pending_count)

    now_ts = time.time()
    next_boundary = (math.floor(now_ts / interval_seconds) + 1) * interval_seconds

    # Estimate how many full windows are needed, then compress the range.
    # Lower compression factor = more aggressive scheduling (more retries).
    # Higher compression factor = more conservative scheduling (fewer retries).
    estimated_windows = max(1, math.ceil(effective_pending / count))
    compression_factor = 0.8
    compressed_windows = max(1.0, estimated_windows * compression_factor)

    distribution_span = min(compressed_windows * interval_seconds, interval_seconds * 5)
    jitter = random.random() * distribution_span
    scheduled_ts = next_boundary + jitter
    return max(1, int(math.ceil(scheduled_ts - now_ts)))


def clean_sender_name(sender_name: str) -> str:
    # Even though we try to properly escape sender names, some characters seem to cause problems when the escaping
    # fails due to some forwardings, etc.

    # Emails with @ in their sender name are rejected by some mailservers (e.g. Microsoft) because it looks like
    # a phishing attempt.
    sender_name = sender_name.replace("@", " ")
    # Emails with : in their sender name are treated by Microsoft like emails with no From header at all, leading
    # to a higher spam likelihood.
    sender_name = sender_name.replace(":", " ")
    # Emails with , in their sender name look like multiple senders
    sender_name = sender_name.replace(",", "")
    # Emails with " in their sender name could be escaped, but somehow create issues in reality
    sender_name = sender_name.replace("\"", "")

    # Emails with excessively long sender names are rejected by some mailservers
    if len(sender_name) > 75:
        sender_name = sender_name[:75] + "..."

    return sender_name


def prefix_subject(settings_holder, subject, highlight=False):
    prefix = settings_holder.settings.get('mail_prefix')
    if prefix and prefix.startswith('[') and prefix.endswith(']'):
        prefix = prefix[1:-1]
    if prefix:
        prefix = f"[{prefix}]"
        if highlight:
            prefix = '<span class="placeholder" title="{}">{}</span>'.format(
                _('This prefix has been set in your event or organizer settings.'),
                escape(prefix)
            )

        subject = f"{prefix} {subject}"
    return subject


def mail(email: Union[str, Sequence[str]], subject: str, template: Union[str, LazyI18nString],
         context: Dict[str, Any] = None, event: Event = None, locale: str = None, order: Order = None,
         position: OrderPosition = None, *, headers: dict = None, sender: str = None, organizer: Organizer = None,
         customer: Customer = None, invoices: Sequence = None, attach_tickets=False, auto_email=True, user=None,
         attach_ical=False, attach_cached_files: Sequence = None, attach_other_files: list=None,
         plain_text_only=False, no_order_links=False, cc: Sequence[str]=None, bcc: Sequence[str]=None,
         sensitive: bool=False):
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

    :param sensitive: If set to ``True``, the email content will not be shown as part of log entries, used e.g. for
                      password resets. Bcc will also not be used.

    :raises MailOrderException: on obvious, immediate failures. Not raising an exception does not necessarily mean
        that the email has been sent, just that it has been queued by the email backend.
    """
    if email == INVALID_ADDRESS:
        return

    if isinstance(template, FormattedString):
        raise TypeError("Cannot pass an already formatted body template")

    if no_order_links and not plain_text_only:
        raise ValueError('If you set no_order_links, you also need to set plain_text_only.')

    settings_holder = event or organizer

    headers = headers or {}
    guid = uuid.uuid4()
    if auto_email:
        headers['X-Auto-Response-Suppress'] = 'OOF, NRN, AutoReply, RN'
        headers['Auto-Submitted'] = 'auto-generated'
    headers.setdefault('X-Mailer', 'pretix')
    headers.setdefault('X-PX-Correlation', str(guid))

    bcc = list(bcc or [])
    if settings_holder and settings_holder.settings.mail_bcc and not sensitive:
        for bcc_mail in settings_holder.settings.mail_bcc.split(','):
            bcc.append(bcc_mail.strip())

    if (settings_holder
            and settings_holder.settings.mail_from in (settings.DEFAULT_FROM_EMAIL, settings.MAIL_FROM_ORGANIZERS)
            and settings_holder.settings.contact_mail and not headers.get('Reply-To')):
        headers['Reply-To'] = settings_holder.settings.contact_mail

    if settings_holder:
        timezone = settings_holder.timezone
    elif user:
        timezone = ZoneInfo(user.timezone)
    else:
        timezone = ZoneInfo(settings.TIME_ZONE)

    if event and attach_tickets and not event.settings.mail_attach_tickets:
        attach_tickets = False

    with language(locale), override(timezone):
        if isinstance(context, dict) and order:
            _autoextend_context(context, order)

        # Build raw content
        content_plain = render_mail(template, context, placeholder_mode=None)
        if settings_holder:
            signature = str(settings_holder.settings.get('mail_text_signature'))
        else:
            signature = ""

        # Build full plain-text body
        if not isinstance(content_plain, FormattedString):
            body_plain = format_map(content_plain, context, mode=SafeFormatter.MODE_RICH_TO_PLAIN)
        else:
            body_plain = content_plain
        body_plain = _wrap_plain_body(body_plain, signature, event, order, position, no_order_links)

        # Build subject
        if not isinstance(subject, FormattedString):
            subject = format_map(subject, context)

        subject = raw_subject = subject.replace('\n', ' ').replace('\r', '')[:900]
        if settings_holder:
            subject = prefix_subject(settings_holder, subject)
        if (order and order.testmode) or (not order and event and event.testmode):
            subject = "[TESTMODE] " + subject

        # Build sender
        sender = _full_sender(sender, event, organizer)

        # Build HTML body
        if plain_text_only:
            body_html = None
        else:
            if event:
                renderer = event.get_html_mail_renderer()
            else:
                renderer = ClassicMailRenderer(None, organizer)

            try:
                if 'context' in inspect.signature(renderer.render).parameters:
                    body_html = renderer.render(content_plain, signature, raw_subject, order, position, context)
                elif 'position' in inspect.signature(renderer.render).parameters:
                    # Backwards compatibility
                    warnings.warn('Email renderer called without context argument because context argument is not '
                                  'supported.',
                                  DeprecationWarning)
                    body_html = renderer.render(content_plain, signature, raw_subject, order, position)
                else:
                    # Backwards compatibility
                    warnings.warn('Email renderer called without position argument because position argument is not '
                                  'supported.',
                                  DeprecationWarning)
                    body_html = renderer.render(content_plain, signature, raw_subject, order)
            except:
                logger.exception('Could not render HTML body')
                body_html = None

        m = OutgoingMail.objects.create(
            organizer=organizer,
            event=event,
            order=order,
            orderposition=position,
            customer=customer,
            user=user,
            to=[email.lower()] if isinstance(email, str) else [e.lower() for e in email],
            cc=[e.lower() for e in cc] if cc else [],
            bcc=[e.lower() for e in bcc] if bcc else [],
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            sender=sender,
            headers=headers or {},
            should_attach_tickets=attach_tickets,
            should_attach_ical=attach_ical,
            should_attach_other_files=attach_other_files or [],
            sensitive=sensitive,
        )
        if invoices and not position:
            m.should_attach_invoices.add(*invoices)
        if attach_cached_files:
            for cf in attach_cached_files:
                if not isinstance(cf, CachedFile):
                    m.should_attach_cached_files.add(CachedFile.objects.get(pk=cf))
                else:
                    m.should_attach_cached_files.add(cf)

        send_task = mail_send_task.si(
            outgoing_mail=m.id
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
def mail_send_task(self, **kwargs) -> bool:
    if "outgoing_mail" in kwargs:
        outgoing_mail_id = kwargs.get("outgoing_mail")
    elif "to" in kwargs:
        # May only occur while upgrading from pretix versions before OutgoingMail when celery tasks are still in-queue
        # during the upgrade. Can be removed after 2026.2.x is released, and then the signature can be changed to
        # mail_send_task(self, *, outgoing_mail)
        with scopes_disabled():
            mail_send(**kwargs)
        return False
    else:
        raise ValueError("Unknown arguments")

    with transaction.atomic():
        try:
            outgoing_mail = OutgoingMail.objects.select_for_update(of=OF_SELF).get(pk=outgoing_mail_id)
        except OutgoingMail.DoesNotExist:
            logger.info(f"Ignoring job for non existing email with ID {outgoing_mail_id}")
            return False
        if outgoing_mail.status == OutgoingMail.STATUS_INFLIGHT:
            logger.info(f"Ignoring job for inflight email {outgoing_mail.guid}")
            return False
        elif outgoing_mail.status not in (OutgoingMail.STATUS_AWAITING_RETRY, OutgoingMail.STATUS_QUEUED):
            logger.info(f"Ignoring job for email {outgoing_mail.guid} in final state {outgoing_mail.status}")
            return False
        outgoing_mail.status = OutgoingMail.STATUS_INFLIGHT
        outgoing_mail.inflight_since = now()
        outgoing_mail.save(update_fields=["status", "inflight_since"])

    # Check rate limit before changing status to INFLIGHT
    try:
        try_acquire_mail_token()
    except MailRateLimitException:
        # Count pending emails to distribute retry times
        pending_count = OutgoingMail.objects.filter(
            status__in=[OutgoingMail.STATUS_QUEUED, OutgoingMail.STATUS_AWAITING_RETRY]
        ).count()

        # Calculate distributed retry countdown
        countdown = get_rate_limit_retry_countdown(pending_count)

        # Update outgoing mail status and retry time (like normal SMTP retries)
        outgoing_mail.error = "Rate limit exceeded"
        outgoing_mail.error_detail = f"{pending_count} emails pending, retry in {countdown}s"
        outgoing_mail.sent = now()
        outgoing_mail.status = OutgoingMail.STATUS_AWAITING_RETRY
        outgoing_mail.retry_after = now() + timedelta(seconds=countdown)
        outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after"])

        max_retry_age_seconds = getattr(settings, "MAIL_RATE_LIMIT_MAX_RETRY_AGE", 24 * 3600)
        if outgoing_mail.created < now() - timedelta(seconds=max_retry_age_seconds):
            outgoing_mail.error = "Rate limit retries exceeded age limit"
            outgoing_mail.error_detail = (
                f"Mail exceeded retry age limit of {max_retry_age_seconds}s while waiting for rate-limit tokens"
            )
            outgoing_mail.sent = now()
            outgoing_mail.status = OutgoingMail.STATUS_FAILED
            outgoing_mail.retry_after = None
            outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after"])
            logger.warning(
                f"Email {outgoing_mail.guid}: Marked as failed after exceeding rate-limit retry age limit"
            )
            return False

        logger.info(f'Email {outgoing_mail.guid}: Rate limit exceeded. {pending_count} emails pending. Retrying in {countdown}s')
        try:
            self.retry(countdown=countdown, max_retries=None)  # throws RetryException, ends function flow
        except MaxRetriesExceededError:
            logger.warning(
                f'Email {outgoing_mail.guid}: Celery reported max retries exceeded during rate-limit retry. '
                'Scheduling a fresh task instead.'
            )
            mail_send_task.apply_async(kwargs={"outgoing_mail": outgoing_mail.pk}, countdown=countdown)
            return False

    headers = dict(outgoing_mail.headers)
    headers.setdefault('X-PX-Correlation', str(outgoing_mail.guid))
    email = CustomEmail(
        subject=outgoing_mail.subject,
        body=outgoing_mail.body_plain,
        from_email=outgoing_mail.sender,
        to=outgoing_mail.to,
        cc=outgoing_mail.cc,
        bcc=outgoing_mail.bcc,
        headers=headers,
    )

    # Rewrite all <img> tags from real URLs or data URLs to inline attachments referred to by content ID
    if outgoing_mail.body_html is not None:
        html_message = SafeMIMEMultipart(_subtype='related', encoding=settings.DEFAULT_CHARSET)
        html_with_cid, cid_images = replace_images_with_cid_paths(outgoing_mail.body_html)
        html_message.attach(SafeMIMEText(html_with_cid, 'html', settings.DEFAULT_CHARSET))
        attach_cid_images(html_message, cid_images, verify_ssl=True)
        email.attach_alternative(html_message, "multipart/related")

    log_target, error_log_action_type = outgoing_mail.log_parameters()
    invoices_attached = []

    with outgoing_mail.scope_manager():
        # Attach tickets
        if outgoing_mail.should_attach_tickets and outgoing_mail.order:
            with language(outgoing_mail.order.locale, outgoing_mail.event.settings.region):
                args = []
                attach_size = 0
                for name, ct in get_tickets_for_order(outgoing_mail.order, base_position=outgoing_mail.orderposition):
                    try:
                        content = ct.file.read()
                        args.append((name, content, ct.type))
                        attach_size += len(content)
                    except Exception as e:
                        # This sometimes fails e.g. with FileNotFoundError. We haven't been able to figure out
                        # why (probably some race condition with ticket cache invalidation?), so retry later.
                        try:
                            logger.exception(f'Could not attach tickets to email {outgoing_mail.guid}, will retry')
                            retry_after = 60
                            outgoing_mail.error = "Tickets not ready"
                            outgoing_mail.error_detail = str(e)
                            outgoing_mail.sent = now()
                            outgoing_mail.status = OutgoingMail.STATUS_AWAITING_RETRY
                            outgoing_mail.retry_after = now() + timedelta(seconds=retry_after)
                            outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after",
                                                              "actual_attachments"])
                            self.retry(max_retries=5, countdown=retry_after)
                        except MaxRetriesExceededError:
                            # Well then, something is really wrong, let's send it without attachment before we
                            # don't send at all
                            logger.exception(f'Too many retries attaching tickets to email {outgoing_mail.guid}, skip attachment')
                            pass

                if attach_size * 1.37 < settings.FILE_UPLOAD_MAX_SIZE_EMAIL_ATTACHMENT - 1024 * 1024:
                    # Do not attach more than (limit - 1 MB) in tickets (1MB space for invoice, email itself, …),
                    # it will bounce way too often.
                    # 1 MB is the buffer for the rest of the email (text, invoice, calendar, pictures)
                    # 1.37 is the factor for base64 encoding https://en.wikipedia.org/wiki/Base64
                    for a in args:
                        try:
                            email.attach(*a)
                        except:
                            pass
                else:
                    outgoing_mail.order.log_action(
                        'pretix.event.order.email.attachments.skipped',
                        data={
                            'subject': 'Attachments skipped',
                            'message': 'Attachment have not been send because {} bytes are likely too large to arrive.'.format(attach_size),
                            'recipient': '',
                            'invoices': [],
                        }
                    )

        # Attach calendar files
        if outgoing_mail.should_attach_ical and outgoing_mail.order:
            fname = re.sub('[^a-zA-Z0-9 ]', '-', unidecode(pgettext('attachment_filename', 'Calendar invite')))
            icals = get_private_icals(
                outgoing_mail.event,
                [outgoing_mail.orderposition] if outgoing_mail.orderposition else outgoing_mail.order.positions.all()
            )
            for i, cal in enumerate(icals):
                name = '{}{}.ics'.format(fname, f'-{i + 1}' if i > 0 else '')
                content = cal.serialize()
                mimetype = 'text/calendar'
                email.attach(name, content, mimetype)

        invoices_to_mark_transmitted = []
        for inv in outgoing_mail.should_attach_invoices.all():
            if inv.file:
                try:
                    # We try to give the invoice a more human-readable name, e.g. "Invoice_ABC-123.pdf" instead of
                    # just "ABC-123.pdf", but we only do so if our currently selected language allows to do this
                    # as ASCII text. For example, we would not want a "فاتورة_" prefix for our filename since this
                    # has shown to cause deliverability problems of the email and deliverability wins.
                    with language(outgoing_mail.order.locale if outgoing_mail.order else inv.locale, outgoing_mail.event.settings.region):
                        filename = pgettext('invoice', 'Invoice {num}').format(num=inv.number).replace(' ', '_') + '.pdf'
                    if not re.match("^[a-zA-Z0-9-_%./,&:# ]+$", filename):
                        filename = inv.number.replace(' ', '_') + '.pdf'
                    filename = re.sub("[^a-zA-Z0-9-_.]+", "_", filename)
                    content = inv.file.file.read()
                    with language(inv.order.locale):
                        email.attach(
                            filename,
                            content,
                            'application/pdf'
                        )
                    invoices_attached.append(inv)
                except Exception:
                    logger.exception(f'Could not attach invoice to email {outgoing_mail.guid}')
                    pass
                else:
                    if inv.transmission_type == "email":
                        # Mark invoice as sent when it was sent to the requested address *either* at the time of invoice
                        # creation *or* as of right now.
                        expected_recipients = [
                            (inv.invoice_to_transmission_info or {}).get("transmission_email_address")
                            or inv.order.email,
                        ]
                        try:
                            expected_recipients.append(
                                (inv.order.invoice_address.transmission_info or {}).get("transmission_email_address")
                                or inv.order.email
                            )
                        except InvoiceAddress.DoesNotExist:
                            pass
                        expected_recipients = {e.lower() for e in expected_recipients if e}
                        if any(t in expected_recipients for t in outgoing_mail.to):
                            invoices_to_mark_transmitted.append(inv)

        for fname in outgoing_mail.should_attach_other_files:
            ftype, _ = mimetypes.guess_type(fname)
            data = default_storage.open(fname).read()
            try:
                email.attach(
                    clean_filename(os.path.basename(fname)),
                    data,
                    ftype
                )
            except:
                logger.exception(f'Could not attach file to email {outgoing_mail.guid}')
                pass

        for cf in outgoing_mail.should_attach_cached_files.all():
            if cf.file:
                try:
                    email.attach(
                        cf.filename,
                        cf.file.file.read(),
                        cf.type,
                    )
                except:
                    logger.exception(f'Could not attach file to email {outgoing_mail.guid}')
                    pass

        outgoing_mail.actual_attachments = [
            {
                "name": a[0],
                "size": len(a[1]),
                "type": a[2],
            } for a in email.attachments
        ]

        try:
            if outgoing_mail.event:
                with outgoing_mail.scope_manager():
                    email = email_filter.send_chained(
                        sender=outgoing_mail.event,
                        chain_kwarg_name='message',
                        message=email,
                        order=outgoing_mail.order,
                        user=outgoing_mail.user,
                        outgoing_mail=outgoing_mail,
                    )

            email = global_email_filter.send_chained(
                sender=outgoing_mail.event,
                chain_kwarg_name='message',
                message=email,
                user=outgoing_mail.user,
                order=outgoing_mail.order,
                organizer=outgoing_mail.organizer,
                customer=outgoing_mail.customer,
                outgoing_mail=outgoing_mail,
            )
        except WithholdMailException as e:
            outgoing_mail.status = OutgoingMail.STATUS_WITHHELD
            outgoing_mail.error = e.error
            outgoing_mail.error_detail = e.error_detail
            outgoing_mail.sent = now()
            outgoing_mail.retry_after = None
            outgoing_mail.actual_attachments = [
                {
                    "name": a[0],
                    "size": len(a[1]),
                    "type": a[2],
                } for a in email.attachments
            ]
            outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
            logger.info(f"Email {outgoing_mail.guid} withheld")
            return False

        # Seems duplicate, but needs to be in this order since plugins might change this
        outgoing_mail.actual_attachments = [
            {
                "name": a[0],
                "size": len(a[1]),
                "type": a[2],
            } for a in email.attachments
        ]
        backend = outgoing_mail.get_mail_backend()
        try:
            backend.send_messages([email])
        except Exception as e:
            logger.exception(f'Error sending email {outgoing_mail.guid}')
            retry_strategy = _retry_strategy(e)
            err, err_detail = _format_error(e)

            outgoing_mail.error = err
            outgoing_mail.error_detail = err_detail
            outgoing_mail.sent = now()

            # Run retries
            try:
                if retry_strategy == "microsoft_concurrency" and settings.HAS_REDIS:
                    from django_redis import get_redis_connection

                    redis_key = "pretix_mail_retry_" + hashlib.sha1(f"{getattr(backend, 'username', '_')}@{getattr(backend, 'host', '_')}".encode()).hexdigest()
                    rc = get_redis_connection("redis")
                    cnt = rc.incr(redis_key)
                    rc.expire(redis_key, 300)

                    max_retries = 10
                    retry_after = min(30 + cnt * 10, 1800)

                    outgoing_mail.status = OutgoingMail.STATUS_AWAITING_RETRY
                    outgoing_mail.retry_after = now() + timedelta(seconds=retry_after)
                    outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
                    self.retry(max_retries=max_retries, countdown=retry_after)  # throws RetryException, ends function flow
                elif retry_strategy in ("microsoft_concurrency", "quick"):
                    max_retries = 5
                    retry_after = [10, 30, 60, 300, 900, 900][self.request.retries]
                    outgoing_mail.status = OutgoingMail.STATUS_AWAITING_RETRY
                    outgoing_mail.retry_after = now() + timedelta(seconds=retry_after)
                    outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
                    self.retry(max_retries=max_retries, countdown=retry_after)  # throws RetryException, ends function flow

                elif retry_strategy == "slow":
                    retry_after = [60, 300, 600, 1200, 1800, 1800][self.request.retries]
                    outgoing_mail.status = OutgoingMail.STATUS_AWAITING_RETRY
                    outgoing_mail.retry_after = now() + timedelta(seconds=retry_after)
                    outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
                    self.retry(max_retries=5, countdown=retry_after)  # throws RetryException, ends function flow

            except MaxRetriesExceededError:
                for i in invoices_to_mark_transmitted:
                    i.set_transmission_failed(provider="email_pdf", data={
                        "reason": "exception",
                        "exception": "{}, max retries exceeded".format(err),
                        "detail": err_detail,
                    })

                if log_target:
                    log_target.log_action(
                        error_log_action_type,
                        data={
                            'subject': f'{err} (max retries exceeded)',
                            'message': err_detail,
                            'recipient': '',
                            'invoices': [],
                        }
                    )

                outgoing_mail.status = OutgoingMail.STATUS_FAILED
                outgoing_mail.sent = now()
                outgoing_mail.retry_after = None
                outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
                return False

            # If we reach this, it's a non-retryable error
            outgoing_mail.status = OutgoingMail.STATUS_FAILED
            outgoing_mail.sent = now()
            outgoing_mail.retry_after = None
            outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "retry_after", "actual_attachments"])
            for i in invoices_to_mark_transmitted:
                i.set_transmission_failed(provider="email_pdf", data={
                    "reason": "exception",
                    "exception": err,
                    "detail": err_detail,
                })
            if log_target:
                log_target.log_action(
                    error_log_action_type,
                    data={
                        'subject': err,
                        'message': err_detail,
                        'recipient': '',
                        'invoices': [],
                    }
                )
            return False
        else:
            outgoing_mail.status = OutgoingMail.STATUS_SENT
            outgoing_mail.error = None
            outgoing_mail.error_detail = None
            outgoing_mail.sent = now()
            outgoing_mail.retry_after = None
            outgoing_mail.save(update_fields=["status", "error", "error_detail", "sent", "actual_attachments", "retry_after"])
            for i in invoices_to_mark_transmitted:
                if i.transmission_status != Invoice.TRANSMISSION_STATUS_COMPLETED:
                    i.transmission_date = now()
                    i.transmission_status = Invoice.TRANSMISSION_STATUS_COMPLETED
                    i.transmission_provider = "email_pdf"
                    i.transmission_info = {
                        "sent": [
                            {
                                "recipients": outgoing_mail.to,
                                "datetime": now().isoformat(),
                            }
                        ]
                    }
                    i.save(update_fields=[
                        "transmission_date", "transmission_provider", "transmission_status",
                        "transmission_info"
                    ])
                elif i.transmission_provider == "email_pdf":
                    i.transmission_info["sent"].append(
                        {
                            "recipients": outgoing_mail.to,
                            "datetime": now().isoformat(),
                        }
                    )
                    i.save(update_fields=[
                        "transmission_info"
                    ])
                i.order.log_action(
                    "pretix.event.order.invoice.sent",
                    data={
                        "full_invoice_no": i.full_invoice_no,
                        "transmission_provider": "email_pdf",
                        "transmission_type": "email",
                        "data": {
                            "recipients": outgoing_mail.to,
                        },
                    }
                )
    return True


def mail_send(to: List[str], subject: str, body: str, html: Optional[str], sender: str,
              event: int | Event = None, position: int | OrderPosition = None, headers: dict = None,
              cc: List[str] = None, bcc: List[str] = None, invoices: List[int | Invoice] = None, order: int | Order = None,
              attach_tickets=False, user: int | User=None, organizer: int | Organizer=None, customer: int | Customer=None,
              attach_ical=False, attach_cached_files: List[int | CachedFile] = None, attach_other_files: List[str] = None):
    """
    Low-level function to send mails, kept for backwards-compatibility. You should usually use mail() instead.
    """
    m = OutgoingMail.objects.create(
        organizer_id=organizer.pk if isinstance(organizer, Organizer) else organizer,
        event_id=event.pk if isinstance(event, Event) else event,
        order_id=order.pk if isinstance(order, Order) else order,
        orderposition_id=position.pk if isinstance(position, OrderPosition) else position,
        customer_id=customer.pk if isinstance(customer, Customer) else customer,
        user_id=user.pk if isinstance(user, User) else user,
        to=[to.lower()] if isinstance(to, str) else [e.lower() for e in to],
        cc=[e.lower() for e in cc] if cc else [],
        bcc=[e.lower() for e in bcc] if bcc else [],
        subject=subject,
        body_plain=body,
        body_html=html,
        sender=sender,
        headers=headers or {},
        should_attach_tickets=attach_tickets,
        should_attach_ical=attach_ical,
        should_attach_other_files=attach_other_files or [],
    )
    if invoices and not position:
        if isinstance(invoices[0], int):
            invoices = Invoice.objects.filter(pk__in=invoices)
        m.should_attach_invoices.add(*invoices)
    if attach_cached_files:
        for cf in attach_cached_files:
            if not isinstance(cf, CachedFile):
                m.should_attach_cached_files.add(CachedFile.objects.get(pk=cf))
            else:
                m.should_attach_cached_files.add(cf)

    mail_send_task.apply_async(kwargs={"outgoing_mail": m.pk})


def render_mail(template, context, placeholder_mode: Optional[int]=SafeFormatter.MODE_RICH_TO_PLAIN):
    if isinstance(template, LazyI18nString):
        body = str(template)
        if context and placeholder_mode:
            body = format_map(body, context, mode=placeholder_mode)
    else:
        tpl = get_template(template)
        context = {
            # Known bug, should behave differently for plain and HTML but we'll fix after security release
            k: v.html if isinstance(v, PlainHtmlAlternativeString) else v
            for k, v in context.items()
        }
        body = FormattedString(tpl.render(context))
    return body


def replace_images_with_cid_paths(body_html):
    from bs4 import BeautifulSoup

    if body_html:
        email = BeautifulSoup(body_html, "lxml")
        cid_images = []
        for image in email.find_all('img'):
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


def _autoextend_context(context, order):
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


def _full_sender(sender_address, event, organizer):
    sender_address = (
        sender_address or
        (event.settings.get('mail_from') if event else None) or
        (organizer.settings.get('mail_from') if organizer else None) or
        settings.MAIL_FROM
    )
    if event:
        sender_name = event.settings.mail_from_name or str(event.name)
    elif organizer:
        sender_name = organizer.settings.mail_from_name or str(organizer.name)
    else:
        sender_name = settings.PRETIX_INSTANCE_NAME

    sender = formataddr((clean_sender_name(sender_name), sender_address))
    return sender


def _wrap_plain_body(content_plain, signature, event, order, position, no_order_links):
    body_plain = content_plain
    body_plain += "\r\n\r\n-- \r\n"

    if signature:
        signature = format_map(signature, {"event": event.name if event else ''})
        body_plain += signature
        body_plain += "\r\n\r\n-- \r\n"

    if event and order and position and not no_order_links:
        body_plain += _(
            "You are receiving this email because someone placed an order for {event} for you."
        ).format(event=event.name)
        body_plain += "\r\n"
        body_plain += _(
            "You can view your order details at the following URL:\n{orderurl}."
        ).replace("\n", "\r\n").format(
            orderurl=build_absolute_uri(
                order.event, 'presale:event.order.position', kwargs={
                    'order': order.code,
                    'secret': position.web_secret,
                    'position': position.positionid,
                }
            )
        )
    elif event and order and not no_order_links:
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
                    'hash': order.email_confirm_secret()
                }
            )
        )
    body_plain += "\r\n"

    return body_plain


def _retry_strategy(e: Exception):
    if isinstance(e, (smtplib.SMTPResponseException, smtplib.SMTPSenderRefused)):
        if e.smtp_code == 432:
            # This is likely Microsoft Exchange Online which has a pretty bad rate limit of max. 3 concurrent
            # SMTP connections which is *easily* exceeded with many celery threads. Just retrying with exponential
            # backoff won't be good enough if we have a lot of emails, instead we'll need to make sure our retry
            # intervals scatter such that the email won't all be retried at the same time again and cause the
            # same problem.
            # See also https://docs.microsoft.com/en-us/exchange/troubleshoot/send-emails/smtp-submission-improvements
            return "microsoft_concurrency"

        if e.smtp_code in (101, 111, 421, 422, 431, 432, 442, 447, 452):
            return "quick"

    elif isinstance(e, smtplib.SMTPRecipientsRefused):
        smtp_codes = [a[0] for a in e.recipients.values()]

        if not any(c >= 500 for c in smtp_codes) or any(b'Message is too large' in a[1] for a in e.recipients.values()):
            # This is not a permanent failure (mailbox full, service unavailable), retry later, but with large
            # intervals. One would think that "Message is too lage" is a permanent failure, but apparently it is not.
            # We have documented cases of emails to Microsoft returning the error occasionally and then later
            # allowing the very same email.
            return "slow"

    elif isinstance(e, OSError) and not isinstance(e, smtplib.SMTPNotSupportedError):
        # Most likely some other kind of temporary failure, retry again (but pretty soon)
        return "quick"


def _format_error(e: Exception):
    if isinstance(e, (smtplib.SMTPResponseException, smtplib.SMTPSenderRefused)):
        return 'SMTP code {}'.format(e.smtp_code), e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
    elif isinstance(e, smtplib.SMTPRecipientsRefused):
        message = []
        for e, val in e.recipients.items():
            message.append(f'{e}: {val[0]} {val[1].decode()}')
        return 'SMTP recipients refudes', '\n'.join(message)
    else:
        return 'Internal error', str(e)


def _is_queue_long(queue_name="mail"):
    """
    Checks an estimate if there is currently a long celery queue for emails. If so,
    there's no reason to retry stuck emails, because they are stuck because of the
    queue and we don't need to add more oil to the fire.

    This does not need to be perfect, as it is safe to run the same task twice, it just
    wastes ressources.
    """
    if not settings.HAS_CELERY:
        return False
    if not settings.CELERY_BROKER_URL.startswith("redis://"):
        return False  # check not supported
    priority_steps = settings.CELERY_BROKER_TRANSPORT_OPTIONS.get("priority_steps", [0])
    sep = settings.CELERY_BROKER_TRANSPORT_OPTIONS.get("sep", ":")
    client = app.broker_connection().channel().client
    queue_length = 0
    for prio in priority_steps:
        if prio:
            qname = f"{queue_name}{sep}{prio}"
        else:
            qname = queue_name
        queue_length += client.llen(qname)

    return queue_length > 100


@receiver(signal=periodic_task)
@scopes_disabled()
def retry_stuck_inflight_mails(sender, **kwargs):
    """
    Retry emails that are stuck in "inflight" state, e.g. their celery task just died.
    """
    with transaction.atomic():
        for m in OutgoingMail.objects.filter(
            status=OutgoingMail.STATUS_INFLIGHT,
            inflight_since__lt=now() - timedelta(hours=1),
        ).select_for_update(of=OF_SELF, skip_locked=connection.features.has_select_for_update_skip_locked):
            m.status = OutgoingMail.STATUS_QUEUED
            m.save()
            mail_send_task.apply_async(kwargs={"outgoing_mail": m.pk})


@receiver(signal=periodic_task)
@scopes_disabled()
def retry_stuck_queued_mails(sender, **kwargs):
    """
    Retry emails that are stuck in "queued" state, e.g. their celery task never started. We do this only
    when there is currently almost no queue, to avoid many tasks being scheduled for the same mail if that
    mail is still waiting in the queue (even if that would be safe, all tasks except the first one would be a no-op,
    but it would create many more useless tasks in a high-load situation).
    """
    if _is_queue_long():
        logger.info("Do not retry stuck mails as the queue is long.")
        return

    for m in OutgoingMail.objects.filter(
        Q(
            status=OutgoingMail.STATUS_QUEUED,
            created__lt=now() - timedelta(hours=1),
        ) | Q(
            status=OutgoingMail.STATUS_AWAITING_RETRY,
            retry_after__lt=now() - timedelta(hours=1),
        )
    ):
        mail_send_task.apply_async(kwargs={"outgoing_mail": m.pk})


@receiver(signal=periodic_task)
@scopes_disabled()
def delete_old_emails(sender, **kwargs):
    """
    OutgoingMail is currently not intended to be an archive, because it would be hard to do in a
    privacy-first design, so we delete after some time.
    """
    cutoff = now() - timedelta(seconds=settings.OUTGOING_MAIL_RETENTION)
    OutgoingMail.objects.filter(
        Q(sent__lt=cutoff) |
        Q(sent__isnull=True, created__lt=cutoff)
    ).delete()
