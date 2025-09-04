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
from django.core.mail import get_connection
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_scopes import scope, scopes_disabled


class OutgoingMail(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_INFLIGHT = "inflight"
    STATUS_AWAWITING_RETRY = "awaiting_retry"
    STATUS_FAILED = "failed"
    STATUS_SENT = "sent"
    STATUS_CHOICES = (
        (STATUS_QUEUED, _("queued")),
        (STATUS_INFLIGHT, _("being sent")),
        (STATUS_AWAWITING_RETRY, _("awaiting retry")),
        (STATUS_FAILED, _("failed")),
        (STATUS_SENT, _("sent")),
    )

    status = models.CharField(max_length=200, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    created = models.DateTimeField(auto_now_add=True)
    sent = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    error_detail = models.TextField(null=True, blank=True)

    organizer = models.ForeignKey(
        'pretixbase.Organizer',
        on_delete=models.CASCADE,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    event = models.ForeignKey(
        'pretixbase.Event',
        on_delete=models.SET_NULL,  # todo think, only for non-queued!
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    order = models.ForeignKey(
        'pretixbase.Order',
        on_delete=models.SET_NULL,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    orderposition = models.ForeignKey(
        'pretixbase.OrderPosition',
        on_delete=models.SET_NULL,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    customer = models.ForeignKey(
        'pretixbase.Customer',
        on_delete=models.SET_NULL,
        related_name='outgoing_mails',
        null=True, blank=True,
    )
    user = models.ForeignKey(
        'pretixbase.User',
        on_delete=models.SET_NULL,
        related_name='outgoing_mails',
        null=True, blank=True,
    )

    subject = models.TextField()
    body_plain = models.TextField()
    body_html = models.TextField()
    sender = models.CharField(max_length=500)
    headers = models.JSONField(default=dict)
    to = models.JSONField(default=list)
    cc = models.JSONField(default=list)
    bcc = models.JSONField(default=list)

    should_attach_invoices = models.ManyToManyField(
        'pretixbase.Invoice',
        related_name='outgoing_mails'
    )
    should_attach_tickets = models.BooleanField(default=False)
    should_attach_ical = models.BooleanField(default=False)
    should_attach_cached_files = models.ManyToManyField(
        'pretixbase.CachedFile',
        related_name='outgoing_mails',
    )  # todo: prevent deletion?
    should_attach_other_files = models.JSONField(default=list)  # todo_ prevent deletion?

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

    def save(self, *args, **kwargs):
        if self.orderposition_id and not self.order_id:
            self.order = self.orderposition.order
        if self.order_id and not self.event_id:
            self.event = self.order.event
        if self.event_id and not self.organizer_id:
            self.organizer = self.event.organizer
        if self.customer_id and not self.organizer_id:
            self.organizer = self.customer.organizer
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
