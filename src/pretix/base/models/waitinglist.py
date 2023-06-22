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
from datetime import timedelta
from typing import Any, Dict, Union

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes import ScopedManager
from i18nfield.strings import LazyI18nString
from phonenumber_field.modelfields import PhoneNumberField

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import User, Voucher
from pretix.base.services.mail import SendMailException, mail, render_mail

from ...helpers.format import format_map
from ...helpers.names import build_name
from .base import LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation


class WaitingListException(Exception):
    pass


class WaitingListEntry(LoggedModel):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="waitinglistentries",
        verbose_name=_("Event"),
    )
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.CASCADE,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    created = models.DateTimeField(
        verbose_name=_("On waiting list since"),
        auto_now_add=True
    )
    name_cached = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        blank=True, null=True,
    )
    name_parts = models.JSONField(
        blank=True, default=dict
    )
    email = models.EmailField(
        verbose_name=_("E-mail address")
    )
    phone = PhoneNumberField(
        null=True, blank=True,
        verbose_name=_("Phone number")
    )
    voucher = models.ForeignKey(
        'Voucher',
        verbose_name=_("Assigned voucher"),
        null=True, blank=True,
        related_name='waitinglistentries',
        on_delete=models.CASCADE
    )
    item = models.ForeignKey(
        Item, related_name='waitinglistentries', on_delete=models.CASCADE,
        verbose_name=_("Product"),
        help_text=_(
            "The product the user waits for."
        )
    )
    variation = models.ForeignKey(
        ItemVariation, related_name='waitinglistentries',
        null=True, blank=True, on_delete=models.CASCADE,
        verbose_name=_("Product variation"),
        help_text=_(
            "The variation of the product selected above."
        )
    )
    locale = models.CharField(
        max_length=190,
        default='en'
    )
    priority = models.IntegerField(default=0)

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Waiting list entry")
        verbose_name_plural = _("Waiting list entries")
        ordering = ('-priority', 'created', 'pk')

    def __str__(self):
        return '%s waits for %s' % (str(self.email), str(self.item))

    def clean(self):
        try:
            WaitingListEntry.clean_duplicate(self.event, self.email, self.item, self.variation, self.subevent, self.pk)
            WaitingListEntry.clean_itemvar(self.event, self.item, self.variation)
            WaitingListEntry.clean_subevent(self.event, self.subevent)
        except ObjectDoesNotExist:
            raise ValidationError('Invalid input')

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields', set())
        if 'name_parts' in update_fields:
            kwargs['update_fields'] = {'name_cached'}.union(kwargs['update_fields'])
        name = self.name
        if name != self.name_cached:
            self.name_cached = name
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'name_cached'}.union(kwargs['update_fields'])

        if self.name_parts is None:
            self.name_parts = {}
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'name_parts'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)

    @property
    def name(self):
        return build_name(self.name_parts, fallback_scheme=lambda: self.event.settings.name_scheme)

    @property
    def name_all_components(self):
        return build_name(self.name_parts, "concatenation_all_components", fallback_scheme=lambda: self.event.settings.name_scheme)

    def send_voucher(self, quota_cache=None, user=None, auth=None):
        availability = (
            self.variation.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
            if self.variation
            else self.item.check_quotas(count_waitinglist=False, subevent=self.subevent, _cache=quota_cache)
        )
        if availability[1] is None or availability[1] < 1:
            raise WaitingListException(_('This product is currently not available.'))

        ev = self.subevent or self.event
        if ev.seat_category_mappings.filter(product=self.item).exists():
            # Generally, we advertise the waiting list to be based on quotas only. This makes it dangerous
            # to use in combination with seating plans. If your event has 50 seats and a quota of 50 and
            # default settings, everything is fine and the waiting list will work as usual. However, as soon
            # as those two numbers diverge, either due to misconfiguration or due to intentional features such
            # as our COVID-19 minimum distance feature, things get ugly. Theoretically, there could be
            # significant quota available but not a single seat! The waiting list would happily send out vouchers
            # which do not work at all. Generally, we consider this a "known bug" and not fixable with the current
            # design of the waiting list and seating features.
            # However, we've put in a simple safeguard that makes sure the waiting list on its own does not screw
            # everything up. Specifically, we will not send out vouchers if the number of available seats is less
            # than the number of valid vouchers *issued through the waiting list*. Things can still go wrong due to
            # manually created vouchers, manually blocked seats or the minimum distance feature,  but this reduces
            # the possible damage a bit.
            num_free_seats_for_product = ev.free_seats().filter(product=self.item).count()
            num_valid_vouchers_for_product = self.event.vouchers.filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now()),
                block_quota=True,
                item_id=self.item_id,
                subevent_id=self.subevent_id,
                waitinglistentries__isnull=False
            ).aggregate(free=Sum(F('max_usages') - F('redeemed')))['free'] or 0
            free_seats = num_free_seats_for_product - num_valid_vouchers_for_product
            if not free_seats:
                raise WaitingListException(_('No seat with this product is currently available.'))

        if self.voucher:
            raise WaitingListException(_('A voucher has already been sent to this person.'))
        if '@' not in self.email:
            raise WaitingListException(_('This entry is anonymized and can no longer be used.'))

        with transaction.atomic():
            e = self.email
            if self.name:
                e += ' / ' + self.name
            v = Voucher.objects.create(
                event=self.event,
                max_usages=1,
                valid_until=now() + timedelta(hours=self.event.settings.waiting_list_hours),
                item=self.item,
                variation=self.variation,
                tag='waiting-list',
                comment=_('Automatically created from waiting list entry for {email}').format(
                    email=e
                ),
                block_quota=True,
                subevent=self.subevent,
            )
            v.log_action('pretix.voucher.added.waitinglist', {
                'item': self.item.pk,
                'variation': self.variation.pk if self.variation else None,
                'tag': 'waiting-list',
                'block_quota': True,
                'valid_until': v.valid_until.isoformat(),
                'max_usages': 1,
                'email': self.email,
                'waitinglistentry': self.pk,
                'subevent': self.subevent.pk if self.subevent else None,
            }, user=user, auth=auth)
            self.log_action('pretix.event.orders.waitinglist.voucher_assigned', user=user, auth=auth)
            self.voucher = v
            self.save()

        with language(self.locale, self.event.settings.region):
            self.send_mail(
                self.event.settings.mail_subject_waiting_list,
                self.event.settings.mail_text_waiting_list,
                get_email_context(
                    event=self.event,
                    waiting_list_entry=self,
                    waiting_list_voucher=v,
                    event_or_subevent=self.subevent or self.event,
                ),
                user=user,
                auth=auth,
            )

    def send_mail(self, subject: Union[str, LazyI18nString], template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.waitinglist.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, auth=None, auto_email=True,
                  attach_other_files: list=None, attach_cached_files: list=None):
        """
        Sends an email to the entry's contact address.

        * Call ``pretix.base.services.mail.mail`` with useful values for the ``event``, ``locale``, and ``recipient``
          parameters.

        * Create a ``LogEntry`` with the email contents.

        :param subject: Subject of the email
        :param template: LazyI18nString or template filename, see ``pretix.base.services.mail.mail`` for more details
        :param context: Dictionary to use for rendering the template
        :param log_entry_type: Key to be used for the log entry
        :param user: Administrative user who triggered this mail to be sent
        :param headers: Dictionary with additional mail headers
        :param sender: Custom email sender.
        """
        if not self.email:
            return

        for k, v in self.event.meta_data.items():
            context['meta_' + k] = v

        with language(self.locale, self.event.settings.region):
            recipient = self.email

            try:
                email_content = render_mail(template, context)
                subject = format_map(subject, context)
                mail(
                    recipient, subject, template, context,
                    self.event,
                    self.locale,
                    headers=headers,
                    sender=sender,
                    auto_email=auto_email,
                    attach_other_files=attach_other_files,
                    attach_cached_files=attach_cached_files,
                )
            except SendMailException:
                raise
            else:
                self.log_action(
                    log_entry_type,
                    user=user,
                    auth=auth,
                    data={
                        'subject': subject,
                        'message': email_content,
                        'recipient': recipient,
                    }
                )

    @staticmethod
    def clean_itemvar(event, item, variation):
        if event != item.event:
            raise ValidationError(_('The selected item does not belong to this event.'))
        if item.has_variations and (not variation or variation.item != item):
            raise ValidationError(_('Please select a specific variation of this product.'))

    @staticmethod
    def clean_subevent(event, subevent):
        if event.has_subevents:
            if not subevent:
                raise ValidationError(_('Subevent cannot be null for event series.'))
            if event != subevent.event:
                raise ValidationError(_('The subevent does not belong to this event.'))
        else:
            if subevent:
                raise ValidationError(_('The subevent does not belong to this event.'))

    @staticmethod
    def clean_duplicate(event, email, item, variation, subevent, pk):
        if WaitingListEntry.objects.filter(
                item=item, variation=variation, email__iexact=email, voucher__isnull=True, subevent=subevent
        ).exclude(pk=pk).count() >= event.settings.waiting_list_limit_per_user:
            raise ValidationError(_('You are already on this waiting list! We will notify '
                                    'you as soon as we have a ticket available for you.'))
