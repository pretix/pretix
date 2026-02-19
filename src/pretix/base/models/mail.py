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
import uuid

from django.core.mail import get_connection
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled


def CASCADE_IF_QUEUED(collector, field, sub_objs, using):
    # If the email is still queued and the thing it is related to vanishes, the email can vanish as well
    cascade_objs = [
        o for o in sub_objs if o.status == OutgoingMail.STATUS_QUEUED
    ]
    if cascade_objs:
        models.CASCADE(collector, field, cascade_objs, using)

    # In all other cases, set to NULL to keep the email on record
    models.SET_NULL(collector, field, [o for o in sub_objs if o not in cascade_objs], using)


class OutgoingMail(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_WITHHELD = "withheld"
    STATUS_INFLIGHT = "inflight"
    STATUS_AWAITING_RETRY = "awaiting_retry"
    STATUS_FAILED = "failed"
    STATUS_SENT = "sent"
    STATUS_BOUNCED = "bounced"
    STATUS_ABORTED = "aborted"
    STATUS_CHOICES = (
        (STATUS_QUEUED, _("queued")),
        (STATUS_INFLIGHT, _("being sent")),
        (STATUS_AWAITING_RETRY, _("awaiting retry")),
        (STATUS_WITHHELD, _("withheld")),  # for plugin use
        (STATUS_FAILED, _("failed")),
        (STATUS_ABORTED, _("aborted")),
        (STATUS_SENT, _("sent")),
        (STATUS_BOUNCED, _("bounced")),  # for plugin use
    )
    STATUS_LIST_ABORTABLE = {
        STATUS_QUEUED,
        STATUS_WITHHELD,
        STATUS_AWAITING_RETRY,
    }
    STATUS_LIST_RETRYABLE = {
        STATUS_FAILED,
        STATUS_WITHHELD,
    }

    # The GUID is a globally unique ID for the email added to a header of the email for later tracing
    # in bug reports etc. We could theoretically also use this as a basis for the Message-ID header, but
    # we currently don't since we are unsure if some intermediary SMTP servers have opinions on setting
    # their own Message-ID headers.
    guid = models.UUIDField(db_index=True, default=uuid.uuid4)

    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    created = models.DateTimeField(auto_now_add=True)

    # sent will be the time the email was sent or the email failed
    sent = models.DateTimeField(null=True, blank=True)

    inflight_since = models.DateTimeField(null=True, blank=True)
    retry_after = models.DateTimeField(null=True, blank=True)

    error = models.TextField(null=True, blank=True)
    error_detail = models.TextField(null=True, blank=True)

    # There is a conflict here between the different purposes of the model. As a system administrator,
    # one wants *all* emails to be persisted as long as possible to debug issues. This means that if
    # e.g. the event or order is deleted, we want SET_NULL behavior. However, in that case, the email
    # would be an "orphan" forever and there's no way to remove the personal information.
    # We try to find a middle-ground with the following behaviour:
    # - The email is always deleted if the entire organizer or user is deleted
    # - The email is always deleted if it has not yet been sent
    # - The email is kept in all other cases
    # This is only an acceptable trade-off since emails are stored for a short period only, and because
    # orders and customers are never deleted during normal operation. If we ever make this a long-term
    # storage / email archive, we'd need to find another way to make sure personal information is removed
    # if personal information of orders etc is removed.
    organizer = models.ForeignKey(
        'pretixbase.Organizer',
        on_delete=models.CASCADE,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    event = models.ForeignKey(
        'pretixbase.Event',
        on_delete=CASCADE_IF_QUEUED,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    order = models.ForeignKey(
        'pretixbase.Order',
        on_delete=CASCADE_IF_QUEUED,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    orderposition = models.ForeignKey(
        'pretixbase.OrderPosition',
        on_delete=CASCADE_IF_QUEUED,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    customer = models.ForeignKey(
        'pretixbase.Customer',
        on_delete=CASCADE_IF_QUEUED,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    user = models.ForeignKey(
        'pretixbase.User',
        on_delete=models.CASCADE,
        related_name='outgoing_mails',
        null=True, blank=True,
    )

    sensitive = models.BooleanField(default=False)
    subject = models.TextField()
    body_plain = models.TextField()
    body_html = models.TextField(null=True)
    sender = models.CharField(max_length=500)
    headers = models.JSONField(default=dict)
    to = models.JSONField(default=list)
    cc = models.JSONField(default=list)
    bcc = models.JSONField(default=list)
    recipient_count = models.IntegerField()

    # We don't store the actual invoices, tickets or calendar invites, so if the email is re-sent at a later time, a
    # newer version of the files might be used. We accept that risk to save on storage and also because the new
    # version might actually be more useful.
    should_attach_invoices = models.ManyToManyField(
        'pretixbase.Invoice',
        related_name='outgoing_mails'
    )
    should_attach_tickets = models.BooleanField(default=False)
    should_attach_ical = models.BooleanField(default=False)

    # clean_cached_files makes sure not to delete these as long as the email is in a retryable state
    should_attach_cached_files = models.ManyToManyField(
        'pretixbase.CachedFile',
        related_name='outgoing_mails',
    )

    # This is used to send files stored in settings. In most cases, these aren't short-lived and should still be there
    # if the email is sent. Otherwise, they will be skipped. We accept that risk.
    should_attach_other_files = models.JSONField(default=list)

    # [{name, type size}] of the attachments we actually setn
    actual_attachments = models.JSONField(default=list)

    class Meta:
        ordering = ('-created',)

    def get_mail_backend(self):
        if self.event:
            return self.event.get_mail_backend()
        elif self.organizer:
            return self.organizer.get_mail_backend()
        else:
            return get_connection(fail_silently=False)

    def scope_manager(self):
        if self.organizer:
            return scope(organizer=self.organizer)  # noqa
        else:
            return scopes_disabled()  # noqa

    @property
    def is_failed(self):
        return self.status in (
            OutgoingMail.STATUS_FAILED,
            OutgoingMail.STATUS_AWAITING_RETRY,
            OutgoingMail.STATUS_BOUNCED,
        )

    def save(self, *args, **kwargs):
        if self.orderposition_id and not self.order_id:
            self.order = self.orderposition.order
        if self.order_id and not self.event_id:
            self.event = self.order.event
        if self.event_id and not self.organizer_id:
            self.organizer = self.event.organizer
        if self.customer_id and not self.organizer_id:
            self.organizer = self.customer.organizer
        self.recipient_count = len(self.to) + len(self.cc) + len(self.bcc)
        super().save(*args, **kwargs)

    def log_parameters(self):
        if self.order:
            error_log_action_type = 'pretix.event.order.email.error'
            log_target = self.order
        elif self.customer:
            error_log_action_type = 'pretix.customer.email.error'
            log_target = self.customer
        elif self.user:
            error_log_action_type = 'pretix.user.email.error'
            log_target = self.user
        else:
            error_log_action_type = 'pretix.email.error'
            log_target = None
        return log_target, error_log_action_type
