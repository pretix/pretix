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
from datetime import datetime, time, timedelta

from django.db import models
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _, ngettext
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.email import get_email_context
from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, OrderPosition, SubEvent,
)
from pretix.base.models.base import LoggingMixin
from pretix.base.services.mail import SendMailException


class ScheduledMail(models.Model):
    STATE_SCHEDULED = 'scheduled'
    STATE_FAILED = 'failed'
    STATE_COMPLETED = 'completed'
    STATE_MISSED = 'missed'

    STATE_CHOICES = [
        (STATE_SCHEDULED, _('scheduled')),
        (STATE_FAILED, _('failed')),
        (STATE_COMPLETED, _('completed')),
        (STATE_MISSED, _('missed')),
    ]

    id = models.BigAutoField(primary_key=True)
    rule = models.ForeignKey("Rule", on_delete=models.CASCADE)
    subevent = models.ForeignKey(SubEvent, null=True, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    last_computed = models.DateTimeField(auto_now_add=True)
    computed_datetime = models.DateTimeField(db_index=True)

    state = models.CharField(max_length=100, choices=STATE_CHOICES, default=STATE_SCHEDULED)
    last_successful_order_id = models.BigIntegerField(null=True)

    class Meta:
        unique_together = ('rule', 'subevent'),

    def save(self, **kwargs):
        if not self.computed_datetime:
            self.recompute()
        super().save(**kwargs)

    def recompute(self):
        if self.state in (self.STATE_COMPLETED, self.STATE_MISSED):
            return

        if self.rule.date_is_absolute:
            self.computed_datetime = self.rule.send_date
        else:
            e = self.subevent or self.event
            o_days = self.rule.send_offset_days
            if not self.rule.offset_is_after:
                o_days *= -1

            offset = timedelta(days=o_days)
            st = self.rule.send_offset_time
            base_time = (e.date_to or e.date_from) if self.rule.offset_to_event_end else e.date_from
            d = base_time.astimezone(self.event.timezone).date() + offset
            self.computed_datetime = make_aware(
                datetime.combine(d, time(hour=st.hour, minute=st.minute, second=st.second, microsecond=0)),
                self.event.timezone,
                is_dst=False,  # prevent AmbiguousTimeError
            )

        self.last_computed = timezone.now()

    def send(self):
        if self.state not in (ScheduledMail.STATE_SCHEDULED, ScheduledMail.STATE_FAILED):
            raise ValueError("Should not be called in this state")

        e = self.event

        orders = e.orders.all()
        limit_products = self.rule.limit_products.values_list('pk', flat=True) if not self.rule.all_products else None

        if self.subevent:
            orders = orders.filter(
                Exists(OrderPosition.objects.filter(order=OuterRef('pk'), subevent=self.subevent))
            )
        elif e.has_subevents:
            return  # This rule should not even exist

        if not self.rule.all_products:
            orders = orders.filter(
                Exists(OrderPosition.objects.filter(order=OuterRef('pk'), item_id__in=limit_products))
            )

        status = [Order.STATUS_PENDING, Order.STATUS_PAID] if self.rule.include_pending else [Order.STATUS_PAID]

        if self.last_successful_order_id:
            orders = orders.filter(
                pk__gt=self.last_successful_order_id
            )

        orders = orders.filter(
            status__in=status,
            require_approval=False,
        ).order_by('pk').select_related('invoice_address').prefetch_related('positions')

        send_to_orders = self.rule.send_to in (Rule.CUSTOMERS, Rule.BOTH)
        send_to_attendees = self.rule.send_to in (Rule.ATTENDEES, Rule.BOTH)

        for o in orders:
            positions = list(o.positions.all())
            o_sent = False

            try:
                ia = o.invoice_address
            except InvoiceAddress.DoesNotExist:
                ia = InvoiceAddress(order=o)

            if send_to_orders and o.email:
                email_ctx = get_email_context(event=e, order=o, position_or_address=ia)
                try:
                    o.send_mail(self.rule.subject, self.rule.template, email_ctx,
                                log_entry_type='pretix.plugins.sendmail.rule.order.email.sent')
                    o_sent = True
                except SendMailException:
                    ...  # ¯\_(ツ)_/¯

            if send_to_attendees:
                if not self.rule.all_products:
                    positions = [p for p in positions if p.item_id in limit_products]
                if self.subevent_id:
                    positions = [p for p in positions if p.subevent_id == self.subevent_id]

                for p in positions:
                    email_ctx = get_email_context(event=e, order=o, position_or_address=ia, position=p)
                    try:
                        if p.attendee_email and (p.attendee_email != o.email or not o_sent):
                            p.send_mail(self.rule.subject, self.rule.template, email_ctx,
                                        log_entry_type='pretix.plugins.sendmail.rule.order.position.email.sent')
                        elif not o_sent and o.email:
                            o.send_mail(self.rule.subject, self.rule.template, email_ctx,
                                        log_entry_type='pretix.plugins.sendmail.rule.order.email.sent')
                            o_sent = True
                    except SendMailException:
                        ...  # ¯\_(ツ)_/¯

            self.last_successful_order_id = o.pk


class Rule(models.Model, LoggingMixin):
    CUSTOMERS = "orders"
    ATTENDEES = "attendees"
    BOTH = "both"

    SEND_TO_CHOICES = [
        (CUSTOMERS, _("Everyone who created a ticket order")),
        (ATTENDEES, _("Every attendee (falling back to the order contact when no attendee email address is given)")),
        (BOTH, _('Both (all order contact addresses and all attendee email addresses)'))
    ]

    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='sendmail_rules')

    subject = I18nCharField(max_length=255, verbose_name=_('Subject'))
    template = I18nTextField(verbose_name=_('Message'))

    all_products = models.BooleanField(default=True, verbose_name=_('All products'))
    limit_products = models.ManyToManyField(Item, blank=True, verbose_name=_('Limit products'))

    include_pending = models.BooleanField(
        default=False,
        verbose_name=_('Include pending orders'),
        help_text=_('By default, only paid orders will receive the email')
    )

    # either send_date or send_offset_* have to be set
    send_date = models.DateTimeField(null=True, blank=True, verbose_name=_('Send date'))
    send_offset_days = models.IntegerField(null=True, blank=True, verbose_name=_('Number of days'))
    send_offset_time = models.TimeField(null=True, blank=True, verbose_name=_('Time of day'))

    date_is_absolute = models.BooleanField(default=True, blank=True)
    offset_to_event_end = models.BooleanField(default=False, blank=True)  # no verbose name because not actually
    offset_is_after = models.BooleanField(default=False, blank=True)      # displayed in any forms

    send_to = models.CharField(max_length=10, choices=SEND_TO_CHOICES, default=CUSTOMERS, verbose_name=_('Send email to'))

    enabled = models.BooleanField(
        default=True,
        verbose_name=_('Enabled'),
        help_text=_('Only enabled rules are actually sent')
    )

    objects = ScopedManager(organizer='event__organizer')

    def save(self, **kwargs):
        is_creation = not self.pk
        super().save(**kwargs)

        create_sms = []
        if self.event.has_subevents:
            for se in self.event.subevents.annotate(has_sm=Exists(ScheduledMail.objects.filter(
                    subevent=OuterRef('pk'), rule=self))).filter(has_sm=False):
                sm = ScheduledMail(rule=self, subevent=se, event=self.event)
                sm.recompute()
                create_sms.append(sm)
            ScheduledMail.objects.bulk_create(create_sms)
        else:
            ScheduledMail.objects.get_or_create(rule=self, event=self.event)

        if not is_creation:
            update_sms = []
            for sm in self.scheduledmail_set.prefetch_related('event').select_related('subevent'):
                if sm in create_sms:
                    continue
                previous = sm.computed_datetime
                sm.recompute()
                if sm.computed_datetime != previous:
                    update_sms.append(sm)

            ScheduledMail.objects.bulk_update(update_sms, ['computed_datetime', 'last_computed'], 100)

    @property
    def human_readable_time(self):
        if self.date_is_absolute:
            d = self.send_date.astimezone(self.event.timezone)
            return _('on {date} at {time}').format(date=date_format(d, 'SHORT_DATE_FORMAT'),
                                                   time=date_format(d, 'TIME_FORMAT'))
        else:
            if self.offset_to_event_end:
                if self.offset_is_after:
                    s = ngettext(
                        '%(count)d day after event end at %(time)s',
                        '%(count)d days after event end at %(time)s',
                        self.send_offset_days
                    ) % {
                        'count': self.send_offset_days,
                        'time': date_format(self.send_offset_time, 'TIME_FORMAT')
                    }
                else:
                    s = ngettext(
                        '%(count)d day before event end at %(time)s',
                        '%(count)d days before event end at %(time)s',
                        self.send_offset_days
                    ) % {
                        'count': self.send_offset_days,
                        'time': date_format(self.send_offset_time, 'TIME_FORMAT')
                    }
            else:
                if self.offset_is_after:
                    s = ngettext(
                        '%(count)d day after event start at %(time)s',
                        '%(count)d days after event start at %(time)s',
                        self.send_offset_days
                    ) % {
                        'count': self.send_offset_days,
                        'time': date_format(self.send_offset_time, 'TIME_FORMAT')
                    }
                else:
                    s = ngettext(
                        '%(count)d day before event start at %(time)s',
                        '%(count)d days before event start at %(time)s',
                        self.send_offset_days
                    ) % {
                        'count': self.send_offset_days,
                        'time': date_format(self.send_offset_time, 'TIME_FORMAT')
                    }
            return s
