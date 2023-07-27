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
# This file contains Apache-licensed contributions copyrighted by: Alexander Schwartz, Ayan Ginet, Daniel, Enrique Saez,
# Flavia Bastos, Jakob Schnell, Sanket Dasgupta, Sohalt, Tobias Kunze, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import hashlib
import json
import logging
import string
from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Union
from zoneinfo import ZoneInfo

import dateutil
import pycountry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import (
    Case, Exists, F, Max, OuterRef, Q, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce, Greatest
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.encoding import escape_uri_path
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_countries.fields import Country
from django_scopes import ScopedManager, scopes_disabled
from i18nfield.strings import LazyI18nString
from phonenumber_field.modelfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers import NumberParseException

from pretix.base.banlist import banned
from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Customer, User
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.services.locking import LOCK_TIMEOUT, NoLockManager
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import order_gracefully_delete

from ...helpers import OF_SELF
from ...helpers.countries import CachedCountries, FastCountryField
from ...helpers.format import format_map
from ...helpers.names import build_name
from ._transactions import (
    _fail, _transactions_mark_order_clean, _transactions_mark_order_dirty,
)
from .base import LockModel, LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation, Question, QuestionOption, Quota

logger = logging.getLogger(__name__)


def generate_secret():
    return get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)


def generate_position_secret():
    raise TypeError("Function no longer exists, use secret generators")


class Order(LockModel, LoggedModel):
    """
    An order is created when a user clicks 'buy' on his cart. It holds
    several OrderPositions and is connected to a user. It has an
    expiration date: If items run out of capacity, orders which are over
    their expiration date might be canceled.

    An order -- like all objects -- has an ID, which is globally unique,
    but also a code, which is shorter and easier to memorize, but only
    unique within a single conference.

    :param code: In addition to the ID, which is globally unique, every
                 order has an order code, which is shorter and easier to
                 memorize, but is only unique within a single conference.
    :type code: str
    :param status: The status of this order. One of:

        * ``STATUS_PENDING``
        * ``STATUS_PAID``
        * ``STATUS_EXPIRED``
        * ``STATUS_CANCELED``

    :param valid_if_pending: Treat this order like a paid order for most purposes (such as check-in), even if it is
                             still unpaid.
    :type valid_if_pending: bool
    :param event: The event this order belongs to
    :type event: Event
    :param customer: The customer this order belongs to
    :type customer: Customer
    :param email: The email of the person who ordered this
    :type email: str
    :param phone: The phone number of the person who ordered this
    :type phone: str
    :param testmode: Whether this is a test mode order
    :type testmode: bool
    :param locale: The locale of this order
    :type locale: str
    :param secret: A secret string that is required to modify the order
    :type secret: str
    :param datetime: The datetime of the order placement
    :type datetime: datetime
    :param expires: The date until this order has to be paid to guarantee the fulfillment
    :type expires: datetime
    :param total: The total amount of the order, including the payment fee
    :type total: decimal.Decimal
    :param comment: An internal comment that will only be visible to staff, and never displayed to the user
    :type comment: str
    :param download_reminder_sent: A field to indicate whether a download reminder has been sent.
    :type download_reminder_sent: boolean
    :param require_approval: If set to ``True``, this order is pending approval by an organizer
    :type require_approval: bool
    :param meta_info: Additional meta information on the order, JSON-encoded.
    :type meta_info: str
    :param sales_channel: Identifier of the sales channel this order was created through.
    :type sales_channel: str
    """

    STATUS_PENDING = "n"
    STATUS_PAID = "p"
    STATUS_EXPIRED = "e"
    STATUS_CANCELED = "c"
    STATUS_REFUNDED = "c"  # deprecated
    STATUS_CHOICE = (
        (STATUS_PENDING, _("pending")),
        (STATUS_PAID, _("paid")),
        (STATUS_EXPIRED, _("expired")),
        (STATUS_CANCELED, _("canceled")),
    )

    code = models.CharField(
        max_length=16,
        verbose_name=_("Order code"),
        db_index=True
    )
    status = models.CharField(
        max_length=3,
        choices=STATUS_CHOICE,
        verbose_name=_("Status"),
        db_index=True
    )
    valid_if_pending = models.BooleanField(
        default=False,
    )
    testmode = models.BooleanField(default=False)
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="orders",
        on_delete=models.CASCADE
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("Customer"),
        related_name="orders",
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    email = models.EmailField(
        null=True, blank=True,
        verbose_name=_('E-mail')
    )
    phone = PhoneNumberField(
        null=True, blank=True,
        verbose_name=_('Phone number'),
    )
    locale = models.CharField(
        null=True, blank=True, max_length=32,
        verbose_name=_('Locale')
    )
    secret = models.CharField(max_length=32, default=generate_secret)
    datetime = models.DateTimeField(
        verbose_name=_("Date"), db_index=False
    )
    cancellation_date = models.DateTimeField(
        null=True, blank=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date")
    )
    total = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Total amount")
    )
    comment = models.TextField(
        blank=True, verbose_name=_("Comment"),
        help_text=_("The text entered in this field will not be visible to the user and is available for your "
                    "convenience.")
    )
    custom_followup_at = models.DateField(
        verbose_name=_("Follow-up date"),
        help_text=_('We\'ll show you this order to be due for a follow-up on this day.'),
        null=True, blank=True
    )
    checkin_attention = models.BooleanField(
        verbose_name=_('Requires special attention'),
        default=False,
        help_text=_('If you set this, the check-in app will show a visible warning that tickets of this order require '
                    'special attention. This will not show any details or custom message, so you need to brief your '
                    'check-in staff how to handle these cases.')
    )
    expiry_reminder_sent = models.BooleanField(
        default=False
    )

    download_reminder_sent = models.BooleanField(
        default=False
    )
    meta_info = models.TextField(
        verbose_name=_("Meta information"),
        null=True, blank=True
    )
    last_modified = models.DateTimeField(
        auto_now=True, db_index=False
    )
    require_approval = models.BooleanField(
        default=False
    )
    sales_channel = models.CharField(max_length=190, default="web")
    email_known_to_work = models.BooleanField(
        default=False,
        verbose_name=_('E-mail address verified')
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ("-datetime", "-pk")
        index_together = [
            ["datetime", "id"],
            ["last_modified", "id"],
        ]

    def __str__(self):
        return self.full_code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'require_approval' not in self.get_deferred_fields() and 'status' not in self.get_deferred_fields():
            self._transaction_key_reset()

    def _transaction_key_reset(self):
        self.__initial_status_paid_or_pending = self.status in (Order.STATUS_PENDING, Order.STATUS_PAID) and not self.require_approval

    def gracefully_delete(self, user=None, auth=None):
        from . import GiftCard, GiftCardTransaction, Membership, Voucher

        if not self.testmode:
            raise TypeError("Only test mode orders can be deleted.")
        self.event.log_action(
            'pretix.event.order.deleted', user=user, auth=auth,
            data={
                'code': self.code,
            }
        )

        order_gracefully_delete.send(self.event, order=self)

        if self.status != Order.STATUS_CANCELED:
            for position in self.positions.all():
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))

        GiftCardTransaction.objects.filter(payment__in=self.payments.all()).update(payment=None)
        GiftCardTransaction.objects.filter(refund__in=self.refunds.all()).update(refund=None)
        GiftCardTransaction.objects.filter(order=self).update(order=None)
        GiftCard.objects.filter(issued_in__in=self.positions.all()).update(issued_in=None)
        Membership.objects.filter(granted_in__order=self, testmode=True).update(granted_in=None)
        OrderPosition.all.filter(order=self, addon_to__isnull=False).delete()
        OrderPosition.all.filter(order=self).delete()
        OrderFee.all.filter(order=self).delete()
        Transaction.objects.filter(order=self).delete()
        self.refunds.all().delete()
        self.payments.all().delete()
        self.event.cache.delete('complain_testmode_orders')
        self.delete()

    def email_confirm_hash(self):
        return hashlib.sha256(settings.SECRET_KEY.encode() + self.secret.encode()).hexdigest()[:9]

    @property
    def fees(self):
        """
        Related manager for all non-canceled fees. Use ``all_fees`` instead if you want
        canceled positions as well.
        """
        return self.all_fees(manager='objects')

    @property
    def custom_followup_due(self):
        return self.custom_followup_at and self.custom_followup_at <= now().astimezone(get_current_timezone()).date()

    @cached_property
    @scopes_disabled()
    def count_positions(self):
        if hasattr(self, 'pcnt'):
            return self.pcnt or 0
        return self.positions.count()

    @property
    def positions(self):
        """
        Related manager for all non-canceled positions. Use ``all_positions`` instead if you want
        canceled positions as well.
        """
        return self.all_positions(manager='objects')

    @cached_property
    def meta_info_data(self):
        if not self.meta_info:
            return {}
        try:
            return json.loads(self.meta_info)
        except TypeError:
            return None

    @property
    @scopes_disabled()
    def payment_refund_sum(self):
        payment_sum = self.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        return payment_sum - refund_sum

    @property
    @scopes_disabled()
    def pending_sum(self):
        total = self.total
        if self.status == Order.STATUS_CANCELED:
            total = Decimal('0.00')
        payment_sum = self.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        return total - payment_sum + refund_sum

    @classmethod
    def annotate_overpayments(cls, qs, results=True, refunds=True, sums=False):
        payment_sum = OrderPayment.objects.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            order=OuterRef('pk')
        ).order_by().values('order').annotate(s=Sum('amount')).values('s')
        refund_sum = OrderRefund.objects.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED),
            order=OuterRef('pk')
        ).order_by().values('order').annotate(s=Sum('amount')).values('s')
        external_refund = OrderRefund.objects.filter(
            state=OrderRefund.REFUND_STATE_EXTERNAL,
            order=OuterRef('pk')
        )
        pending_refund = OrderRefund.objects.filter(
            state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT),
            order=OuterRef('pk')
        )
        payment_sum_sq = Subquery(payment_sum, output_field=models.DecimalField(decimal_places=2, max_digits=13))
        refund_sum_sq = Subquery(refund_sum, output_field=models.DecimalField(decimal_places=2, max_digits=13))
        if sums:
            qs = qs.annotate(
                payment_sum=payment_sum_sq,
                refund_sum=refund_sum_sq,
            )
            qs = qs.annotate(
                computed_payment_refund_sum=Coalesce(payment_sum_sq, Decimal('0.00')) - Coalesce(refund_sum_sq, Decimal('0.00')),
            )

        qs = qs.annotate(
            pending_sum_t=F('total') - Coalesce(payment_sum_sq, Decimal('0.00')) + Coalesce(refund_sum_sq, Decimal('0.00')),
            pending_sum_rc=-1 * Coalesce(payment_sum_sq, Decimal('0.00')) + Coalesce(refund_sum_sq, Decimal('0.00')),
        )
        if refunds:
            qs = qs.annotate(
                has_external_refund=Exists(external_refund),
                has_pending_refund=Exists(pending_refund),
            )
        if results:
            qs = qs.annotate(
                is_overpaid=Case(
                    When(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=-1e-8),
                         then=Value(1)),
                    When(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=-1e-8),
                         then=Value(1)),
                    default=Value(0),
                    output_field=models.IntegerField()
                ),
                is_pending_with_full_payment=Case(
                    When(Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=1e-8)
                         & Q(require_approval=False),
                         then=Value(1)),
                    default=Value(0),
                    output_field=models.IntegerField()
                ),
                is_underpaid=Case(
                    When(Q(status=Order.STATUS_PAID) & Q(pending_sum_t__gt=1e-8),
                         then=Value(1)),
                    When(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__gt=1e-8),
                         then=Value(1)),
                    default=Value(0),
                    output_field=models.IntegerField()
                )
            )
        return qs

    @property
    def full_code(self):
        """
        An order code which is unique among all events of a single organizer,
        built by concatenating the event slug and the order code.
        """
        return '{event}-{code}'.format(event=self.event.slug.upper(), code=self.code)

    def save(self, **kwargs):
        if 'update_fields' in kwargs:
            kwargs['update_fields'] = {'last_modified'}.union(kwargs['update_fields'])
        if not self.code:
            self.assign_code()
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'code'}.union(kwargs['update_fields'])
        if not self.datetime:
            self.datetime = now()
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'datetime'}.union(kwargs['update_fields'])
        if not self.expires:
            self.set_expires()
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'expires'}.union(kwargs['update_fields'])

        is_new = not self.pk
        update_fields = kwargs.get('update_fields', [])
        if 'require_approval' not in self.get_deferred_fields() and 'status' not in self.get_deferred_fields():
            status_paid_or_pending = self.status in (Order.STATUS_PENDING, Order.STATUS_PAID) and not self.require_approval
            if status_paid_or_pending != self.__initial_status_paid_or_pending:
                _transactions_mark_order_dirty(self.pk, using=kwargs.get('using', None))
        elif (
            not kwargs.get('force_save_with_deferred_fields', None) and
            (not update_fields or ('require_approval' not in update_fields and 'status' not in update_fields))
        ):
            _fail("It is unsafe to call save() on an OrderFee with deferred fields since we can't check if you missed "
                  "creating a transaction. Call save(force_save_with_deferred_fields=True) if you really want to do "
                  "this.")

        r = super().save(**kwargs)

        if is_new:
            _transactions_mark_order_dirty(self.pk, using=kwargs.get('using', None))

        return r

    def touch(self):
        self.save(update_fields=['last_modified'])

    def set_expires(self, now_dt=None, subevents=None):
        now_dt = now_dt or now()
        tz = ZoneInfo(self.event.settings.timezone)
        mode = self.event.settings.get('payment_term_mode')
        if mode == 'days':
            exp_by_date = now_dt.astimezone(tz) + timedelta(days=self.event.settings.get('payment_term_days', as_type=int))
            exp_by_date = exp_by_date.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=0)
            if self.event.settings.get('payment_term_weekdays'):
                if exp_by_date.weekday() == 5:
                    exp_by_date += timedelta(days=2)
                elif exp_by_date.weekday() == 6:
                    exp_by_date += timedelta(days=1)
        elif mode == 'minutes':
            exp_by_date = now_dt.astimezone(tz) + timedelta(minutes=self.event.settings.get('payment_term_minutes', as_type=int))
        else:
            raise ValueError("'payment_term_mode' has an invalid value '{}'.".format(mode))

        self.expires = exp_by_date

        term_last = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if term_last:
            if self.event.has_subevents and subevents:
                terms = [
                    term_last.datetime(se).date()
                    for se in subevents
                ]
                if not terms:
                    return
                term_last = min(terms)
            else:
                term_last = term_last.datetime(self.event).date()
            term_last = make_aware(datetime.combine(
                term_last,
                time(hour=23, minute=59, second=59)
            ), tz)
            if term_last < self.expires:
                self.expires = term_last

    @cached_property
    def tax_total(self):
        return (self.positions.aggregate(s=Sum('tax_value'))['s'] or 0) + (self.fees.aggregate(s=Sum('tax_value'))['s'] or 0)

    @property
    def net_total(self):
        return self.total - self.tax_total

    def cancel_allowed(self):
        return (
            self.status in (Order.STATUS_PENDING, Order.STATUS_PAID, Order.STATUS_EXPIRED) and self.count_positions
        )

    @cached_property
    def user_change_deadline(self):
        until = self.event.settings.get('change_allow_user_until', as_type=RelativeDateWrapper)
        if until:
            if self.event.has_subevents:
                terms = [
                    until.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ]
                return min(terms) if terms else None
            else:
                return until.datetime(self.event)

    @cached_property
    def user_cancel_deadline(self):
        if self.status == Order.STATUS_PAID and self.total != Decimal('0.00'):
            until = self.event.settings.get('cancel_allow_user_paid_until', as_type=RelativeDateWrapper)
        else:
            until = self.event.settings.get('cancel_allow_user_until', as_type=RelativeDateWrapper)
        if until:
            if self.event.has_subevents:
                terms = [
                    until.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ]
                return min(terms) if terms else None
            else:
                return until.datetime(self.event)

    @cached_property
    def user_cancel_fee(self):
        fee = Decimal('0.00')
        if self.status == Order.STATUS_PAID:
            if self.event.settings.cancel_allow_user_paid_keep_fees:
                fee += self.fees.filter(
                    fee_type__in=(OrderFee.FEE_TYPE_PAYMENT, OrderFee.FEE_TYPE_SHIPPING, OrderFee.FEE_TYPE_SERVICE,
                                  OrderFee.FEE_TYPE_CANCELLATION)
                ).aggregate(
                    s=Sum('value')
                )['s'] or 0
            if self.event.settings.cancel_allow_user_paid_keep_percentage:
                fee += self.event.settings.cancel_allow_user_paid_keep_percentage / Decimal('100.0') * (self.total - fee)
            if self.event.settings.cancel_allow_user_paid_keep:
                fee += self.event.settings.cancel_allow_user_paid_keep
        else:
            if self.event.settings.cancel_allow_user_unpaid_keep_fees:
                fee += self.fees.filter(
                    fee_type__in=(OrderFee.FEE_TYPE_PAYMENT, OrderFee.FEE_TYPE_SHIPPING, OrderFee.FEE_TYPE_SERVICE,
                                  OrderFee.FEE_TYPE_CANCELLATION)
                ).aggregate(
                    s=Sum('value')
                )['s'] or 0
            if self.event.settings.cancel_allow_user_unpaid_keep_percentage:
                fee += self.event.settings.cancel_allow_user_unpaid_keep_percentage / Decimal('100.0') * (self.total - fee)
            if self.event.settings.cancel_allow_user_unpaid_keep:
                fee += self.event.settings.cancel_allow_user_unpaid_keep
        return round_decimal(min(fee, self.total), self.event.currency)

    @property
    @scopes_disabled()
    def user_change_allowed(self) -> bool:
        """
        Returns whether or not this order can be canceled by the user.
        """
        from .checkin import Checkin
        from .items import ItemAddOn

        if self.status not in (Order.STATUS_PENDING, Order.STATUS_PAID) or not self.count_positions:
            return False

        if self.cancellation_requests.exists():
            return False

        if self.require_approval:
            return False

        positions = list(
            self.positions.all().annotate(
                has_variations=Exists(ItemVariation.objects.filter(item_id=OuterRef('item_id'))),
                has_checkin=Exists(Checkin.objects.filter(position_id=OuterRef('pk')))
            ).select_related('item').prefetch_related('issued_gift_cards')
        )
        if self.event.settings.change_allow_user_if_checked_in:
            cancelable = all([op.item.allow_cancel for op in positions])
        else:
            cancelable = all([op.item.allow_cancel and not op.has_checkin for op in positions])
        if not cancelable or not positions:
            return False
        for op in positions:
            if op.issued_gift_cards.all():
                return False
        if self.user_change_deadline and now() > self.user_change_deadline:
            return False

        return (
            (self.event.settings.change_allow_user_variation and any([op.has_variations for op in positions])) or
            (self.event.settings.change_allow_user_addons and ItemAddOn.objects.filter(base_item_id__in=[op.item_id for op in positions]).exists())
        )

    @property
    @scopes_disabled()
    def user_cancel_allowed(self) -> bool:
        """
        Returns whether or not this order can be canceled by the user.
        """
        from .checkin import Checkin

        if self.cancellation_requests.exists() or not self.cancel_allowed():
            return False
        positions = list(
            self.positions.all().annotate(
                has_checkin=Exists(Checkin.objects.filter(position_id=OuterRef('pk')))
            ).select_related('item').prefetch_related('issued_gift_cards')
        )
        cancelable = all([op.item.allow_cancel and not op.has_checkin and not op.blocked for op in positions])
        if not cancelable or not positions:
            return False
        for op in positions:
            for gc in op.issued_gift_cards.all():
                if gc.value != op.price:
                    return False
            if op.granted_memberships.with_usages().filter(usages__gt=0):
                return False
        if self.user_cancel_deadline and now() > self.user_cancel_deadline:
            return False

        if self.status == Order.STATUS_PAID:
            if self.total == Decimal('0.00'):
                return self.event.settings.cancel_allow_user
            return self.event.settings.cancel_allow_user_paid
        elif self.payment_refund_sum > Decimal('0.00'):
            return False
        elif self.status == Order.STATUS_PENDING:
            return self.event.settings.cancel_allow_user
        return False

    def propose_auto_refunds(self, amount: Decimal, payments: list=None):
        # Algorithm to choose which payments are to be refunded to create the least hassle
        payments = payments or self.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        for p in payments:
            if p.payment_provider:
                p.full_refund_possible = p.payment_provider.payment_refund_supported(p)
                p.partial_refund_possible = p.payment_provider.payment_partial_refund_supported(p)
                p.propose_refund = Decimal('0.00')
                p.available_amount = p.amount - p.refunded_amount
            else:
                p.full_refund_possible = False
                p.partial_refund_possible = False
                p.propose_refund = Decimal('0.00')
                p.available_amount = Decimal('0.00')

        unused_payments = set(p for p in payments if p.full_refund_possible or p.partial_refund_possible)
        to_refund = amount
        proposals = {}

        while to_refund and unused_payments:
            bigger = sorted([
                p for p in unused_payments
                if p.available_amount > to_refund
                and p.partial_refund_possible
            ], key=lambda p: p.available_amount)
            same = [
                p for p in unused_payments
                if p.available_amount == to_refund
                and (p.full_refund_possible or p.partial_refund_possible)
            ]
            smaller = sorted([
                p for p in unused_payments
                if p.available_amount < to_refund
                and (p.full_refund_possible or p.partial_refund_possible)
            ], key=lambda p: p.available_amount, reverse=True)
            if same:
                payment = same[0]
                proposals[payment] = payment.available_amount
                to_refund -= payment.available_amount
                unused_payments.remove(payment)
            elif bigger:
                payment = bigger[0]
                proposals[payment] = to_refund
                to_refund -= to_refund
                unused_payments.remove(payment)
            elif smaller:
                payment = smaller[0]
                proposals[payment] = payment.available_amount
                to_refund -= payment.available_amount
                unused_payments.remove(payment)
            else:
                break
        return proposals

    @staticmethod
    def normalize_code(code, is_fallback=False):
        d = {
            '2': 'Z',
            '4': 'A',
            '5': 'S',
            '6': 'G',
        }
        if is_fallback:
            d['8'] = 'B'
            # 8 has been removed from the character set only in 2021, which means there are a lot of order codes
            # with an 8 in it around. We only want to replace this when this is used in a fallback.
        tr = str.maketrans(d)
        return code.upper().translate(tr)

    def assign_code(self):
        # This omits some character pairs completely because they are hard to read even on screens (1/I and O/0)
        # and includes only one of two characters for some pairs because they are sometimes hard to distinguish in
        # handwriting (2/Z, 4/A, 5/S, 6/G, 8/B). This allows for better detection e.g. in incoming wire transfers that
        # might include OCR'd handwritten text
        charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ379')
        iteration = 0
        length = settings.ENTROPY['order_code']
        while True:
            code = get_random_string(length=length, allowed_chars=charset)
            iteration += 1

            if banned(code):
                continue

            if self.testmode:
                # Subtle way to recognize test orders while debugging: They all contain a 0 at the second place,
                # even though zeros are not used outside test mode.
                code = code[0] + "0" + code[2:]

            if not Order.objects.filter(event__organizer=self.event.organizer, code=code).exists():
                self.code = code
                return

            if iteration > 20:
                # Safeguard: If we don't find an unused and non-banlisted code within 20 iterations, we increase
                # the length.
                length += 1
                iteration = 0

    @property
    def modify_deadline(self):
        modify_deadline = self.event.settings.get('last_order_modification_date', as_type=RelativeDateWrapper)
        if self.event.has_subevents and modify_deadline:
            dates = [
                modify_deadline.datetime(se)
                for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
            ]
            return min(dates) if dates else None
        elif modify_deadline:
            return modify_deadline.datetime(self.event)
        return None

    @property
    def can_modify_answers(self) -> bool:
        """
        ``True`` if the user can change the question answers / attendee names that are
        related to the order. This checks order status and modification deadlines. It also
        returns ``False`` if there are no questions that can be answered.
        """
        from .checkin import Checkin

        if self.status not in (Order.STATUS_PENDING, Order.STATUS_PAID, Order.STATUS_EXPIRED):
            return False

        modify_deadline = self.modify_deadline
        if modify_deadline is not None and now() > modify_deadline:
            return False

        positions = list(
            self.positions.all().annotate(
                has_checkin=Exists(Checkin.objects.filter(position_id=OuterRef('pk')))
            ).select_related('item').prefetch_related('item__questions')
        )
        if not self.event.settings.allow_modifications_after_checkin:
            for cp in positions:
                if cp.has_checkin:
                    return False

        if self.event.settings.get('invoice_address_asked', as_type=bool):
            return True
        ask_names = self.event.settings.get('attendee_names_asked', as_type=bool)
        for cp in positions:
            if (cp.item.ask_attendee_data and ask_names) or cp.item.questions.all():
                return True

        return False  # nothing there to modify

    @property
    def is_expired_by_time(self):
        return (
            self.status == Order.STATUS_PENDING and not self.require_approval and self.expires < now()
            and not self.event.settings.get('payment_term_expire_automatically')
        )

    @property
    def ticket_download_date(self):
        """
        Returns the first date the tickets for this order can be downloaded or ``None`` if there is no
        restriction.
        """
        dl_date = self.event.settings.get('ticket_download_date', as_type=RelativeDateWrapper)
        if dl_date:
            if self.event.has_subevents:
                dates = [
                    dl_date.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ]
                dl_date = min(dates) if dates else None
            else:
                dl_date = dl_date.datetime(self.event)
        return dl_date

    @property
    def ticket_download_available(self):
        return self.event.settings.ticket_download and (
            self.event.settings.ticket_download_date is None
            or self.ticket_download_date is None
            or now() > self.ticket_download_date
        ) and (
            self.status == Order.STATUS_PAID
            or (
                (self.valid_if_pending or self.event.settings.ticket_download_pending) and
                self.status == Order.STATUS_PENDING and
                not self.require_approval
            )
        )

    @property
    def payment_term_last(self):
        tz = ZoneInfo(self.event.settings.timezone)
        term_last = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if term_last:
            if self.event.has_subevents:
                terms = [
                    term_last.datetime(se).date()
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ]
                if terms:
                    term_last = min(terms)
                else:
                    return None
            else:
                term_last = term_last.datetime(self.event).date()
            term_last = make_aware(datetime.combine(
                term_last,
                time(hour=23, minute=59, second=59)
            ), tz)
        return term_last

    @property
    def payment_term_expire_date(self):
        delay = self.event.settings.get('payment_term_expire_delay_days', as_type=int)
        if not delay:  # performance saver + backwards compatibility
            return self.expires

        term_last = self.payment_term_last
        if term_last and self.expires > term_last:  # backwards compatibility
            return self.expires

        expires = self.expires.date() + timedelta(days=delay)
        if self.event.settings.get('payment_term_weekdays'):
            if expires.weekday() == 5:
                expires += timedelta(days=2)
            elif expires.weekday() == 6:
                expires += timedelta(days=1)

        tz = ZoneInfo(self.event.settings.timezone)
        expires = make_aware(datetime.combine(
            expires,
            time(hour=23, minute=59, second=59)
        ), tz)
        if term_last:
            return min(expires, term_last)
        else:
            return expires

    def _can_be_paid(self, count_waitinglist=True, ignore_date=False, force=False) -> Union[bool, str]:
        error_messages = {
            'late_lastdate': _("The payment can not be accepted as the last date of payments configured in the "
                               "payment settings is over."),
            'late': _("The payment can not be accepted as the order is expired and you configured that no late "
                      "payments should be accepted in the payment settings."),
            'require_approval': _('This order is not yet approved by the event organizer.')
        }
        if not force:
            if self.require_approval:
                return error_messages['require_approval']
            term_last = self.payment_term_last
            if term_last and not ignore_date:
                if now() > term_last:
                    return error_messages['late_lastdate']

        if self.status == self.STATUS_PENDING:
            return True
        if not self.event.settings.get('payment_term_accept_late') and not ignore_date and not force:
            return error_messages['late']

        return self._is_still_available(count_waitinglist=count_waitinglist, force=force)

    def _is_still_available(self, now_dt: datetime=None, count_waitinglist=True, force=False,
                            check_voucher_usage=False, check_memberships=False) -> Union[bool, str]:
        from pretix.base.services.memberships import (
            validate_memberships_in_order,
        )

        error_messages = {
            'unavailable': _('The ordered product "{item}" is no longer available.'),
            'seat_unavailable': _('The seat "{seat}" is no longer available.'),
            'voucher_budget': _('The voucher "{voucher}" no longer has sufficient budget.'),
            'voucher_usages': _('The voucher "{voucher}" has been used in the meantime.'),
        }
        now_dt = now_dt or now()
        positions = list(self.positions.all().select_related('item', 'variation', 'seat', 'voucher'))
        quota_cache = {}
        v_budget = {}
        v_usage = Counter()
        try:
            if check_memberships:
                try:
                    validate_memberships_in_order(self.customer, positions, self.event, lock=False, testmode=self.testmode)
                except ValidationError as e:
                    raise Quota.QuotaExceededException(e.message)

            for i, op in enumerate(positions):
                if op.seat:
                    if not op.seat.is_available(ignore_orderpos=op):
                        raise Quota.QuotaExceededException(error_messages['seat_unavailable'].format(seat=op.seat))
                if force:
                    continue

                if op.voucher and op.voucher.budget is not None and op.voucher_budget_use:
                    if op.voucher not in v_budget:
                        v_budget[op.voucher] = op.voucher.budget - op.voucher.budget_used()
                    disc = op.voucher_budget_use
                    if disc > v_budget[op.voucher]:
                        raise Quota.QuotaExceededException(error_messages['voucher_budget'].format(
                            voucher=op.voucher.code
                        ))
                    v_budget[op.voucher] -= disc

                if op.voucher and check_voucher_usage:
                    v_usage[op.voucher.pk] += 1
                    if v_usage[op.voucher.pk] + op.voucher.redeemed > op.voucher.max_usages:
                        raise Quota.QuotaExceededException(error_messages['voucher_usages'].format(
                            voucher=op.voucher.code
                        ))

                quotas = list(op.quotas)
                if len(quotas) == 0:
                    raise Quota.QuotaExceededException(error_messages['unavailable'].format(
                        item=str(op.item) + (' - ' + str(op.variation) if op.variation else '')
                    ))

                for quota in quotas:
                    if quota.id not in quota_cache:
                        quota_cache[quota.id] = quota
                        quota.cached_availability = quota.availability(now_dt, count_waitinglist=count_waitinglist)[1]
                    else:
                        # Use cached version
                        quota = quota_cache[quota.id]
                    if quota.cached_availability is not None:
                        quota.cached_availability -= 1
                        if quota.cached_availability < 0:
                            # This quota is sold out/currently unavailable, so do not sell this at all
                            raise Quota.QuotaExceededException(error_messages['unavailable'].format(
                                item=str(op.item) + (' - ' + str(op.variation) if op.variation else '')
                            ))
        except Quota.QuotaExceededException as e:
            return str(e)
        return True

    def send_mail(self, subject: Union[str, LazyI18nString], template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.event.order.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, invoices: list=None,
                  auth=None, attach_tickets=False, position: 'OrderPosition'=None, auto_email=True,
                  attach_ical=False, attach_other_files: list=None, attach_cached_files: list=None):
        """
        Sends an email to the user that placed this order. Basically, this method does two things:

        * Call ``pretix.base.services.mail.mail`` with useful values for the ``event``, ``locale``, ``recipient`` and
          ``order`` parameters.

        * Create a ``LogEntry`` with the email contents.

        :param subject: Subject of the email
        :param template: LazyI18nString or template filename, see ``pretix.base.services.mail.mail`` for more details
        :param context: Dictionary to use for rendering the template
        :param log_entry_type: Key to be used for the log entry
        :param user: Administrative user who triggered this mail to be sent
        :param headers: Dictionary with additional mail headers
        :param sender: Custom email sender.
        :param attach_tickets: Attach tickets of this order, if they are existing and ready to download
        :param attach_ical: Attach relevant ICS files
        :param position: An order position this refers to. If given, no invoices will be attached, the tickets will
                         only be attached for this position and child positions, the link will only point to the
                         position and the attendee email will be used if available.
        """
        from pretix.base.services.mail import (
            SendMailException, mail, render_mail,
        )

        if not self.email and not (position and position.attendee_email):
            return

        for k, v in self.event.meta_data.items():
            context['meta_' + k] = v

        with language(self.locale, self.event.settings.region):
            recipient = self.email
            if position and position.attendee_email:
                recipient = position.attendee_email

            try:
                email_content = render_mail(template, context)
                subject = format_map(subject, context)
                mail(
                    recipient, subject, template, context,
                    self.event, self.locale, self, headers=headers, sender=sender,
                    invoices=invoices, attach_tickets=attach_tickets,
                    position=position, auto_email=auto_email, attach_ical=attach_ical,
                    attach_other_files=attach_other_files, attach_cached_files=attach_cached_files,
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
                        'position': position.positionid if position else None,
                        'recipient': recipient,
                        'invoices': [i.pk for i in invoices] if invoices else [],
                        'attach_tickets': attach_tickets,
                        'attach_ical': attach_ical,
                    }
                )

    def resend_link(self, user=None, auth=None):
        with language(self.locale, self.event.settings.region):
            email_template = self.event.settings.mail_text_resend_link
            email_context = get_email_context(event=self.event, order=self)
            email_subject = self.event.settings.mail_subject_resend_link
            self.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.resend', user=user, auth=auth,
                attach_tickets=True,
            )

    @property
    def positions_with_tickets(self):
        for op in self.positions.select_related('item'):
            if not op.generate_ticket:
                continue
            yield op

    def create_transactions(self, is_new=False, positions=None, fees=None, dt_now=None, migrated=False,
                            _backfill_before_cancellation=False, save=True):
        dt_now = dt_now or now()

        # Count the transactions we already have
        current_transaction_count = Counter()
        if not is_new:
            for t in Transaction.objects.filter(order=self):  # do not use related manager, we want to avoid cached data
                current_transaction_count[Transaction.key(t)] += t.count

        # Count the transactions we'd actually need
        target_transaction_count = Counter()
        if (_backfill_before_cancellation or self.status in (Order.STATUS_PENDING, Order.STATUS_PAID)) and not self.require_approval:
            positions = self.positions.all() if positions is None else positions
            for p in positions:
                if p.canceled and not _backfill_before_cancellation:
                    continue
                target_transaction_count[Transaction.key(p)] += 1
                p._transaction_key_reset()

            fees = self.fees.all() if fees is None else fees
            for f in fees:
                if f.canceled and not _backfill_before_cancellation:
                    continue
                target_transaction_count[Transaction.key(f)] += 1
                f._transaction_key_reset()

        keys = set(target_transaction_count.keys()) | set(current_transaction_count.keys())
        create = []
        for k in keys:
            positionid, itemid, variationid, subeventid, price, taxrate, taxruleid, taxvalue, feetype, internaltype = k
            d = target_transaction_count[k] - current_transaction_count[k]
            if d:
                create.append(Transaction(
                    order=self,
                    datetime=dt_now,
                    migrated=migrated,
                    positionid=positionid,
                    count=d,
                    item_id=itemid,
                    variation_id=variationid,
                    subevent_id=subeventid,
                    price=price,
                    tax_rate=taxrate,
                    tax_rule_id=taxruleid,
                    tax_value=taxvalue,
                    fee_type=feetype,
                    internal_type=internaltype,
                ))
        create.sort(key=lambda t: (0 if t.count < 0 else 1, t.positionid or 0))
        if save:
            Transaction.objects.bulk_create(create)
        self._transaction_key_reset()
        _transactions_mark_order_clean(self.pk)
        return create


def answerfile_name(instance, filename: str) -> str:
    secret = get_random_string(length=32, allowed_chars=string.ascii_letters + string.digits)
    event = (instance.cartposition if instance.cartposition else instance.orderposition.order).event
    return 'cachedfiles/answers/{org}/{ev}/{secret}.{filename}'.format(
        org=event.organizer.slug,
        ev=event.slug,
        secret=secret,
        filename=escape_uri_path(filename),
    )


class QuestionAnswer(models.Model):
    """
    The answer to a Question, connected to an OrderPosition or CartPosition.

    :param orderposition: The order position this is related to, or null if this is
                          related to a cart position.
    :type orderposition: OrderPosition
    :param cartposition: The cart position this is related to, or null if this is related
                         to an order position.
    :type cartposition: CartPosition
    :param question: The question this is an answer for
    :type question: Question
    :param answer: The actual answer data
    :type answer: str
    """
    orderposition = models.ForeignKey(
        'OrderPosition', null=True, blank=True,
        related_name='answers', on_delete=models.CASCADE
    )
    cartposition = models.ForeignKey(
        'CartPosition', null=True, blank=True,
        related_name='answers', on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question, related_name='answers', on_delete=models.CASCADE
    )
    options = models.ManyToManyField(
        QuestionOption, related_name='answers', blank=True
    )
    answer = models.TextField()
    file = models.FileField(
        null=True, blank=True, upload_to=answerfile_name,
        max_length=255
    )

    objects = ScopedManager(organizer='question__event__organizer')

    class Meta:
        unique_together = [['orderposition', 'question'], ['cartposition', 'question']]

    @property
    def backend_file_url(self):
        if self.file:
            if self.orderposition:
                return reverse('control:event.order.download.answer', kwargs={
                    'code': self.orderposition.order.code,
                    'event': self.orderposition.order.event.slug,
                    'organizer': self.orderposition.order.event.organizer.slug,
                    'answer': self.pk,
                })
        return ""

    @property
    def frontend_file_url(self):
        from pretix.multidomain.urlreverse import eventreverse

        if self.file:
            if self.orderposition:
                url = eventreverse(self.orderposition.order.event, 'presale:event.order.download.answer', kwargs={
                    'order': self.orderposition.order.code,
                    'secret': self.orderposition.order.secret,
                    'answer': self.pk,
                })
            else:
                url = eventreverse(self.cartposition.event, 'presale:event.cart.download.answer', kwargs={
                    'answer': self.pk,
                })

            return url
        return ""

    @property
    def is_image(self):
        return any(self.file.name.lower().endswith(e) for e in ('.jpg', '.png', '.gif', '.tiff', '.bmp', '.jpeg'))

    @property
    def file_name(self):
        return self.file.name.split('.', 1)[-1]

    def __str__(self):
        if self.question.type == Question.TYPE_BOOLEAN and self.answer == "True":
            return str(_("Yes"))
        elif self.question.type == Question.TYPE_BOOLEAN and self.answer == "False":
            return str(_("No"))
        elif self.question.type == Question.TYPE_FILE:
            return str(_("<file>"))
        elif self.question.type == Question.TYPE_DATETIME and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                if self.orderposition:
                    tz = ZoneInfo(self.orderposition.order.event.settings.timezone)
                    d = d.astimezone(tz)
                return date_format(d, "SHORT_DATETIME_FORMAT")
            except ValueError:
                return self.answer
        elif self.question.type == Question.TYPE_DATE and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                return date_format(d, "SHORT_DATE_FORMAT")
            except ValueError:
                return self.answer
        elif self.question.type == Question.TYPE_TIME and self.answer:
            try:
                d = dateutil.parser.parse(self.answer)
                return date_format(d, "TIME_FORMAT")
            except ValueError:
                return self.answer
        elif self.question.type == Question.TYPE_COUNTRYCODE and self.answer:
            return Country(self.answer).name or self.answer
        elif self.question.type == Question.TYPE_PHONENUMBER and self.answer:
            try:
                return PhoneNumber.from_string(self.answer).as_international
            except NumberParseException:
                return self.answer
        else:
            return self.answer

    def save(self, *args, **kwargs):
        if self.orderposition and self.cartposition:
            raise ValueError('QuestionAnswer cannot be linked to an order and a cart position at the same time.')
        if self.orderposition:
            self.orderposition.order.touch()
        super().save(*args, **kwargs)

    def delete(self, **kwargs):
        if self.orderposition:
            self.orderposition.order.touch()
        super().delete(**kwargs)


class AbstractPosition(models.Model):
    """
    A position can either be one line of an order or an item placed in a cart.

    :param subevent: The date in the event series, if event series are enabled
    :type subevent: SubEvent
    :param item: The selected item
    :type item: Item
    :param variation: The selected ItemVariation or null, if the item has no variations
    :type variation: ItemVariation
    :param datetime: The datetime this item was put into the cart
    :type datetime: datetime
    :param expires: The date until this item is guaranteed to be reserved
    :type expires: datetime
    :param price: The price of this item
    :type price: decimal.Decimal
    :param attendee_name_parts: The parts of the attendee's name, if entered.
    :type attendee_name_parts: str
    :param attendee_name_cached: The concatenated version of the attendee's name, if entered.
    :type attendee_name_cached: str
    :param attendee_email: The attendee's email, if entered.
    :type attendee_email: str
    :param voucher: A voucher that has been applied to this sale
    :type voucher: Voucher
    :param meta_info: Additional meta information on the position, JSON-encoded.
    :type meta_info: str
    :param seat: Seat, if reserved seating is used.
    :type seat: Seat
    """
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.PROTECT,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    item = models.ForeignKey(
        Item,
        verbose_name=_("Item"),
        on_delete=models.PROTECT
    )
    variation = models.ForeignKey(
        ItemVariation,
        null=True, blank=True,
        verbose_name=_("Variation"),
        on_delete=models.PROTECT
    )
    price = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Price")
    )
    attendee_name_cached = models.CharField(
        max_length=255,
        verbose_name=_("Attendee name"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )
    attendee_name_parts = models.JSONField(
        blank=True, default=dict
    )
    attendee_email = models.EmailField(
        verbose_name=_("Attendee email"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )
    voucher = models.ForeignKey(
        'Voucher', null=True, blank=True, on_delete=models.PROTECT
    )
    used_membership = models.ForeignKey(
        'Membership', null=True, blank=True, on_delete=models.PROTECT
    )
    addon_to = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='addons'
    )
    meta_info = models.TextField(
        verbose_name=_("Meta information"),
        null=True, blank=True
    )
    seat = models.ForeignKey(
        'Seat', null=True, blank=True, on_delete=models.PROTECT
    )
    is_bundled = models.BooleanField(default=False)

    discount = models.ForeignKey(
        'Discount', null=True, blank=True, on_delete=models.RESTRICT
    )

    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'), null=True)
    street = models.TextField(verbose_name=_('Address'), blank=True, null=True)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=True, null=True)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=True, null=True)
    country = FastCountryField(verbose_name=_('Country'), blank=True, blank_label=_('Select country'), null=True)
    state = models.CharField(max_length=255, verbose_name=pgettext_lazy('address', 'State'), blank=True, null=True)

    class Meta:
        abstract = True

    @property
    def meta_info_data(self):
        if self.meta_info:
            return json.loads(self.meta_info)
        else:
            return {}

    @property
    def item_and_variation(self):
        return self.item, self.variation

    @meta_info_data.setter
    def meta_info_data(self, d):
        self.meta_info = json.dumps(d)

    def cache_answers(self, all=True):
        """
        Creates two properties on the object.
        (1) answ: a dictionary of question.id → answer string
        (2) questions: a list of Question objects, extended by an 'answer' property
        """
        self.answ = {}
        for a in getattr(self, 'answerlist', self.answers.all()):  # use prefetch_related cache from get_cart
            self.answ[a.question_id] = a

        # We need to clone our question objects, otherwise we will override the cached
        # answers of other items in the same cart if the question objects have been
        # selected via prefetch_related
        if not all:
            if hasattr(self.item, 'questions_to_ask'):
                questions = list(copy.copy(q) for q in self.item.questions_to_ask)
            else:
                questions = list(copy.copy(q) for q in self.item.questions.filter(ask_during_checkin=False,
                                                                                  hidden=False))
        else:
            questions = list(copy.copy(q) for q in self.item.questions.all())

        question_cache = {
            q.pk: q for q in questions
        }

        def question_is_visible(parentid, qvals):
            if parentid not in question_cache:
                return False
            parentq = question_cache[parentid]
            if parentq.dependency_question_id and not question_is_visible(parentq.dependency_question_id, parentq.dependency_values):
                return False
            if parentid not in self.answ:
                return False
            return (
                ('True' in qvals and self.answ[parentid].answer == 'True')
                or ('False' in qvals and self.answ[parentid].answer == 'False')
                or (any(qval in [o.identifier for o in self.answ[parentid].options.all()] for qval in qvals))
            )

        self.questions = []
        for q in questions:
            if q.id in self.answ:
                q.answer = self.answ[q.id]
                q.answer.question = q  # cache object
            else:
                q.answer = ""
            if not q.dependency_question_id or question_is_visible(q.dependency_question_id, q.dependency_values):
                self.questions.append(q)

    @property
    def net_price(self):
        return self.price - self.tax_value

    @property
    def quotas(self):
        return (self.item.quotas.filter(subevent=self.subevent)
                if self.variation is None
                else self.variation.quotas.filter(subevent=self.subevent))

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields', set())
        if 'attendee_name_parts' in update_fields:
            kwargs['update_fields'] = {'attendee_name_cached'}.union(kwargs['update_fields'])

        name = self.attendee_name
        if name != self.attendee_name_cached:
            self.attendee_name_cached = name
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'attendee_name_cached'}.union(kwargs['update_fields'])

        if self.attendee_name_parts is None:
            self.attendee_name_parts = {}
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'attendee_name_parts'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)

    @property
    def attendee_name(self):
        return build_name(self.attendee_name_parts, fallback_scheme=lambda: self.event.settings.name_scheme)

    @property
    def attendee_name_all_components(self):
        return build_name(self.attendee_name_parts, "concatenation_all_components", fallback_scheme=lambda: self.event.settings.name_scheme)

    @property
    def state_name(self):
        sd = pycountry.subdivisions.get(code='{}-{}'.format(self.country, self.state))
        if sd:
            return sd.name
        return self.state

    @property
    def state_for_address(self):
        from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS
        if not self.state or str(self.country) not in COUNTRIES_WITH_STATE_IN_ADDRESS:
            return ""
        if COUNTRIES_WITH_STATE_IN_ADDRESS[str(self.country)][1] == 'long':
            return self.state_name
        return self.state

    def address_format(self):
        lines = [
            self.attendee_name,
            self.company,
            self.street,
            (self.zipcode or '') + ' ' + (self.city or '') + ' ' + (self.state_for_address or ''),
            self.country.name
        ]
        lines = [r.strip() for r in lines if r]
        return '\n'.join(lines).strip()

    def requires_approval(self, invoice_address=None):
        if self.item.require_approval:
            return True
        if self.variation and self.variation.require_approval:
            return True
        if self.item.tax_rule and self.item.tax_rule._require_approval(invoice_address):
            return True
        return False


class OrderPayment(models.Model):
    """
    Represents a payment or payment attempt for an order.


    :param id: A globally unique ID for this payment
    :type id:
    :param local_id: An ID of this payment, counting from one for every order independently.
    :type local_id: int
    :param state: The state of the payment, one of ``created``, ``pending``, ``confirmed``, ``failed``,
      ``canceled``, or ``refunded``.
    :type state: str
    :param amount: The payment amount
    :type amount: Decimal
    :param order: The order that is paid
    :type order: Order
    :param created: The creation time of this record
    :type created: datetime
    :param payment_date: The completion time of this payment
    :type payment_date: datetime
    :param provider: The payment provider in use
    :type provider: str
    :param info: Provider-specific meta information (in JSON format)
    :type info: str
    :param fee: The ``OrderFee`` object used to track the fee for this order.
    :type fee: pretix.base.models.OrderFee
    :param process_initiated: Only for internal use inside pretix.presale to check which payments have started
                              the execution process.
    :type process_initiated: bool
    """
    PAYMENT_STATE_CREATED = 'created'
    PAYMENT_STATE_PENDING = 'pending'
    PAYMENT_STATE_CONFIRMED = 'confirmed'
    PAYMENT_STATE_FAILED = 'failed'
    PAYMENT_STATE_CANCELED = 'canceled'
    PAYMENT_STATE_REFUNDED = 'refunded'

    PAYMENT_STATES = (
        (PAYMENT_STATE_CREATED, pgettext_lazy('payment_state', 'created')),
        (PAYMENT_STATE_PENDING, pgettext_lazy('payment_state', 'pending')),
        (PAYMENT_STATE_CONFIRMED, pgettext_lazy('payment_state', 'confirmed')),
        (PAYMENT_STATE_CANCELED, pgettext_lazy('payment_state', 'canceled')),
        (PAYMENT_STATE_FAILED, pgettext_lazy('payment_state', 'failed')),
        (PAYMENT_STATE_REFUNDED, pgettext_lazy('payment_state', 'refunded')),
    )
    local_id = models.PositiveIntegerField()
    state = models.CharField(
        max_length=190, choices=PAYMENT_STATES
    )
    amount = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Amount")
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='payments',
        on_delete=models.PROTECT
    )
    created = models.DateTimeField(
        auto_now_add=True
    )
    payment_date = models.DateTimeField(
        null=True, blank=True
    )
    provider = models.CharField(
        null=True, blank=True,
        max_length=255,
        verbose_name=_("Payment provider")
    )
    info = models.TextField(
        verbose_name=_("Payment information"),
        null=True, blank=True
    )
    fee = models.ForeignKey(
        'OrderFee',
        null=True, blank=True, related_name='payments', on_delete=models.SET_NULL
    )
    migrated = models.BooleanField(default=False)
    process_initiated = models.BooleanField(
        null=True  # null = created before this field was introduced
    )

    objects = ScopedManager(organizer='order__event__organizer')

    class Meta:
        ordering = ('local_id',)

    def __str__(self):
        return self.full_id

    @property
    def info_data(self):
        """
        This property allows convenient access to the data stored in the ``info``
        attribute by automatically encoding and decoding the content as JSON.
        """
        return json.loads(self.info) if self.info else {}

    @info_data.setter
    def info_data(self, d):
        self.info = json.dumps(d, sort_keys=True)

    @cached_property
    def payment_provider(self):
        """
        Cached access to an instance of the payment provider in use.
        """
        return self.order.event.get_payment_providers(cached=True).get(self.provider)

    @transaction.atomic()
    def _mark_paid_inner(self, force, count_waitinglist, user, auth, ignore_date=False, overpaid=False):
        from pretix.base.signals import order_paid
        can_be_paid = self.order._can_be_paid(count_waitinglist=count_waitinglist, ignore_date=ignore_date, force=force)
        if can_be_paid is not True:
            self.order.log_action('pretix.event.order.quotaexceeded', {
                'message': can_be_paid
            }, user=user, auth=auth)
            raise Quota.QuotaExceededException(can_be_paid)
        status_change = self.order.status != Order.STATUS_PENDING
        self.order.status = Order.STATUS_PAID
        self.order.save(update_fields=['status'])

        self.order.log_action('pretix.event.order.paid', {
            'provider': self.provider,
            'info': self.info,
            'date': self.payment_date,
            'force': force
        }, user=user, auth=auth)

        if overpaid:
            self.order.log_action('pretix.event.order.overpaid', {}, user=user, auth=auth)
        order_paid.send(self.order.event, order=self.order)
        if status_change:
            self.order.create_transactions()

    def fail(self, info=None, user=None, auth=None, log_data=None, send_mail=True):
        """
        Marks the order as failed and sets info to ``info``, but only if the order is in ``created`` or ``pending``
        state. This is equivalent to setting ``state`` to ``OrderPayment.PAYMENT_STATE_FAILED`` and logging a failure,
        but it adds strong database logging since we do not want to report a failure for an order that has just
        been marked as paid.
        :param send_mail: Whether an email should be sent to the user about this event (default: ``True``).
        """
        with transaction.atomic():
            locked_instance = OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=self.pk)
            if locked_instance.state not in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
                # Race condition detected, this payment is already confirmed
                logger.info('Failed payment {} but ignored due to likely race condition.'.format(
                    self.full_id,
                ))
                return False

            if isinstance(info, str):
                locked_instance.info = info
            elif info:
                locked_instance.info_data = info
            locked_instance.state = OrderPayment.PAYMENT_STATE_FAILED
            locked_instance.save(update_fields=['state', 'info'])

        self.refresh_from_db()
        self.order.log_action('pretix.event.order.payment.failed', {
            'local_id': self.local_id,
            'provider': self.provider,
            'info': info,
            'data': log_data,
        }, user=user, auth=auth)

        if send_mail:
            with language(self.order.locale, self.order.event.settings.region):
                email_subject = self.order.event.settings.mail_subject_order_payment_failed
                email_template = self.order.event.settings.mail_text_order_payment_failed
                email_context = get_email_context(event=self.order.event, order=self.order)
                self.order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.payment_failed', user=user, auth=auth,
                )

        return True

    def confirm(self, count_waitinglist=True, send_mail=True, force=False, user=None, auth=None, mail_text='',
                ignore_date=False, lock=True, payment_date=None, generate_invoice=True):
        """
        Marks the payment as complete. If possible, this also marks the order as paid if no further
        payment is required

        :param count_waitinglist: Whether, when calculating quota, people on the waiting list should be taken into
                                  consideration (default: ``True``).
        :type count_waitinglist: boolean
        :param force: Whether this payment should be marked as paid even if no remaining
                      quota is available (default: ``False``).
        :param ignore_date: Whether this order should be marked as paid even when the last date of payments is over.
        :type force: boolean
        :param send_mail: Whether an email should be sent to the user about this event (default: ``True``).
        :type send_mail: boolean
        :param user: The user who performed the change
        :param auth: The API auth token that performed the change
        :param mail_text: Additional text to be included in the email
        :type mail_text: str
        :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
        """
        with transaction.atomic():
            locked_instance = OrderPayment.objects.select_for_update(of=OF_SELF).get(pk=self.pk)
            if locked_instance.state == self.PAYMENT_STATE_CONFIRMED:
                # Race condition detected, this payment is already confirmed
                logger.info('Confirmed payment {} but ignored due to likely race condition.'.format(
                    self.full_id,
                ))
                return

            locked_instance.state = self.PAYMENT_STATE_CONFIRMED
            locked_instance.payment_date = payment_date or now()
            locked_instance.info = self.info  # required for backwards compatibility
            locked_instance.save(update_fields=['state', 'payment_date', 'info'])

            # Do a cheap manual "refresh from db" on non-complex fields
            for field in self._meta.concrete_fields:
                if not field.is_relation:
                    setattr(self, field.attname, getattr(locked_instance, field.attname))

        self.refresh_from_db()

        self.order.log_action('pretix.event.order.payment.confirmed', {
            'local_id': self.local_id,
            'provider': self.provider,
        }, user=user, auth=auth)

        if self.order.status in (Order.STATUS_PAID, Order.STATUS_CANCELED):
            logger.info('Confirmed payment {} but order is in status {}.'.format(self.full_id, self.order.status))
            return

        payment_sum = self.order.payments.filter(
            state__in=(self.PAYMENT_STATE_CONFIRMED, self.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.order.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        if payment_sum - refund_sum < self.order.total:
            logger.info('Confirmed payment {} but payment sum is {} and refund sum is {}.'.format(
                self.full_id, payment_sum, refund_sum
            ))
            return

        self._mark_order_paid(count_waitinglist, send_mail, force, user, auth, mail_text, ignore_date, lock, payment_sum - refund_sum,
                              generate_invoice)

    def _mark_order_paid(self, count_waitinglist=True, send_mail=True, force=False, user=None, auth=None, mail_text='',
                         ignore_date=False, lock=True, payment_refund_sum=0, allow_generate_invoice=True):
        from pretix.base.services.invoices import (
            generate_invoice, invoice_qualified,
        )

        if (self.order.status == Order.STATUS_PENDING and self.order.expires > now() + timedelta(seconds=LOCK_TIMEOUT * 2)) or not lock:
            # Performance optimization. In this case, there's really no reason to lock everything and an atomic
            # database transaction is more than enough.
            lockfn = NoLockManager
        else:
            lockfn = self.order.event.lock

        with lockfn():
            self._mark_paid_inner(force, count_waitinglist, user, auth, overpaid=payment_refund_sum > self.order.total,
                                  ignore_date=ignore_date)

        invoice = None
        if invoice_qualified(self.order) and allow_generate_invoice:
            invoices = self.order.invoices.filter(is_cancellation=False).count()
            cancellations = self.order.invoices.filter(is_cancellation=True).count()
            gen_invoice = (
                (invoices == 0 and self.order.event.settings.get('invoice_generate') in ('True', 'paid')) or
                0 < invoices <= cancellations
            )
            if gen_invoice:
                invoice = generate_invoice(
                    self.order,
                    trigger_pdf=not send_mail or not self.order.event.settings.invoice_email_attachment
                )

        if send_mail and self.order.sales_channel in self.order.event.settings.mail_sales_channel_placed_paid:
            self._send_paid_mail(invoice, user, mail_text)
            if self.order.event.settings.mail_send_order_paid_attendee:
                for p in self.order.positions.all():
                    if p.addon_to_id is None and p.attendee_email and p.attendee_email != self.order.email:
                        self._send_paid_mail_attendee(p, user)

    def _send_paid_mail_attendee(self, position, user):
        from pretix.base.services.mail import SendMailException

        with language(self.order.locale, self.order.event.settings.region):
            email_template = self.order.event.settings.mail_text_order_paid_attendee
            email_subject = self.order.event.settings.mail_subject_order_paid_attendee
            email_context = get_email_context(event=self.order.event, order=self.order, position=position)
            try:
                position.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_paid', user,
                    invoices=[],
                    attach_tickets=True,
                    attach_ical=self.order.event.settings.mail_attach_ical
                )
            except SendMailException:
                logger.exception('Order paid email could not be sent')

    def _send_paid_mail(self, invoice, user, mail_text):
        from pretix.base.services.mail import SendMailException

        with language(self.order.locale, self.order.event.settings.region):
            email_template = self.order.event.settings.mail_text_order_paid
            email_subject = self.order.event.settings.mail_subject_order_paid
            email_context = get_email_context(event=self.order.event, order=self.order, payment_info=mail_text)
            try:
                self.order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_paid', user,
                    invoices=[invoice] if invoice and self.order.event.settings.invoice_email_attachment else [],
                    attach_tickets=True,
                    attach_ical=self.order.event.settings.mail_attach_ical
                )
            except SendMailException:
                logger.exception('Order paid email could not be sent')

    @property
    def refunded_amount(self):
        """
        The sum of all refund amounts in ``done``, ``transit``, or ``created`` states associated
        with this payment.
        """
        return self.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    @property
    def full_id(self):
        """
        The full human-readable ID of this payment, constructed by the order code and the ``local_id``
        field with ``-P-`` in between.
        :return:
        """
        return '{}-P-{}'.format(self.order.code, self.local_id)

    def save(self, *args, **kwargs):
        if not self.local_id:
            self.local_id = (self.order.payments.aggregate(m=Max('local_id'))['m'] or 0) + 1
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'local_id'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)

    def create_external_refund(self, amount=None, execution_date=None, info='{}'):
        """
        This should be called to create an OrderRefund object when a refund has triggered
        by an external source, e.g. when a credit card payment has been refunded by the
        credit card provider.

        :param amount: Amount to refund. If not given, the full payment amount will be used.
        :type amount: Decimal
        :param execution_date: Date of the refund. Defaults to the current time.
        :type execution_date: datetime
        :param info: Additional information, defaults to ``"{}"``.
        :type info: str
        :return: OrderRefund
        """
        r = self.order.refunds.create(
            state=OrderRefund.REFUND_STATE_EXTERNAL,
            source=OrderRefund.REFUND_SOURCE_EXTERNAL,
            amount=amount if amount is not None else self.amount,
            order=self.order,
            payment=self,
            execution_date=execution_date or now(),
            provider=self.provider,
            info=info
        )
        self.order.log_action('pretix.event.order.refund.created.externally', {
            'local_id': r.local_id,
            'provider': r.provider,
        })

        if self.order.pending_sum + r.amount == Decimal('0.00'):
            r.done()

        return r


class OrderRefund(models.Model):
    """
    Represents a refund or refund attempt for an order.

    :param id: A globally unique ID for this refund
    :type id:
    :param local_id: An ID of this refund, counting from one for every order independently.
    :type local_id: int
    :param state: The state of the refund, one of ``created``, ``transit``, ``external``, ``canceled``,
      ``failed``, or ``done``.
    :type state: str
    :param source: How this refund was started, one of ``buyer``, ``admin``, or ``external``.
    :param amount: The refund amount
    :type amount: Decimal
    :param order: The order that is refunded
    :type order: Order
    :param created: The creation time of this record
    :type created: datetime
    :param execution_date: The completion time of this refund
    :type execution_date: datetime
    :param provider: The payment provider in use
    :type provider: str
    :param info: Provider-specific meta information in JSON format
    :type info: dict
    """
    # REFUND_STATE_REQUESTED = 'requested'
    # REFUND_STATE_APPROVED = 'approved'
    REFUND_STATE_EXTERNAL = 'external'
    REFUND_STATE_TRANSIT = 'transit'
    REFUND_STATE_DONE = 'done'
    # REFUND_STATE_REJECTED = 'rejected'
    REFUND_STATE_CANCELED = 'canceled'
    REFUND_STATE_CREATED = 'created'
    REFUND_STATE_FAILED = 'failed'

    REFUND_STATES = (
        # (REFUND_STATE_REQUESTED, pgettext_lazy('refund_state', 'requested')),
        # (REFUND_STATE_APPROVED, pgettext_lazy('refund_state', 'approved')),
        (REFUND_STATE_EXTERNAL, pgettext_lazy('refund_state', 'started externally')),
        (REFUND_STATE_CREATED, pgettext_lazy('refund_state', 'created')),
        (REFUND_STATE_TRANSIT, pgettext_lazy('refund_state', 'in transit')),
        (REFUND_STATE_DONE, pgettext_lazy('refund_state', 'done')),
        (REFUND_STATE_FAILED, pgettext_lazy('refund_state', 'failed')),
        # (REFUND_STATE_REJECTED, pgettext_lazy('refund_state', 'rejected')),
        (REFUND_STATE_CANCELED, pgettext_lazy('refund_state', 'canceled')),
    )

    REFUND_SOURCE_BUYER = 'buyer'
    REFUND_SOURCE_ADMIN = 'admin'
    REFUND_SOURCE_EXTERNAL = 'external'

    REFUND_SOURCES = (
        (REFUND_SOURCE_ADMIN, pgettext_lazy('refund_source', 'Organizer')),
        (REFUND_SOURCE_BUYER, pgettext_lazy('refund_source', 'Customer')),
        (REFUND_SOURCE_EXTERNAL, pgettext_lazy('refund_source', 'External')),
    )

    local_id = models.PositiveIntegerField()
    state = models.CharField(
        max_length=190, choices=REFUND_STATES
    )
    source = models.CharField(
        max_length=190, choices=REFUND_SOURCES
    )
    amount = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Amount")
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='refunds',
        on_delete=models.PROTECT
    )
    payment = models.ForeignKey(
        OrderPayment,
        null=True, blank=True,
        related_name='refunds',
        on_delete=models.PROTECT
    )
    created = models.DateTimeField(
        auto_now_add=True
    )
    execution_date = models.DateTimeField(
        null=True, blank=True
    )
    provider = models.CharField(
        null=True, blank=True,
        max_length=255,
        verbose_name=_("Payment provider")
    )
    comment = models.TextField(
        verbose_name=_("Refund reason"),
        help_text=_('May be shown to the end user or used e.g. as part of a payment reference.'),
        null=True, blank=True
    )
    info = models.TextField(
        verbose_name=_("Payment information"),
        null=True, blank=True
    )

    objects = ScopedManager(organizer='order__event__organizer')

    class Meta:
        ordering = ('local_id',)

    def __str__(self):
        return self.full_id

    @property
    def info_data(self):
        """
        This property allows convenient access to the data stored in the ``info``
        attribute by automatically encoding and decoding the content as JSON.
        """
        return json.loads(self.info) if self.info else {}

    @info_data.setter
    def info_data(self, d):
        self.info = json.dumps(d, sort_keys=True)

    @cached_property
    def payment_provider(self):
        """
        Cached access to an instance of the payment provider in use.
        """
        return self.order.event.get_payment_providers().get(self.provider)

    @transaction.atomic
    def done(self, user=None, auth=None):
        """
        Marks the refund as complete. This does not modify the state of the order.

        :param user: The user who performed the change
        :param auth: The API auth token that performed the change
        """
        self.state = self.REFUND_STATE_DONE
        self.execution_date = self.execution_date or now()
        self.save()

        self.order.log_action('pretix.event.order.refund.done', {
            'local_id': self.local_id,
            'provider': self.provider,
        }, user=user, auth=auth)

        if self.payment and self.payment.refunded_amount >= self.payment.amount:
            self.payment.state = OrderPayment.PAYMENT_STATE_REFUNDED
            self.payment.save(update_fields=['state'])

    @property
    def full_id(self):
        """
        The full human-readable ID of this refund, constructed by the order code and the ``local_id``
        field with ``-R-`` in between.
        :return:
        """
        return '{}-R-{}'.format(self.order.code, self.local_id)

    def save(self, *args, **kwargs):
        if not self.local_id:
            self.local_id = (self.order.refunds.aggregate(m=Max('local_id'))['m'] or 0) + 1
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'local_id'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)


class ActivePositionManager(ScopedManager(organizer='order__event__organizer').__class__):
    def get_queryset(self):
        return super().get_queryset().filter(canceled=False)


class OrderFee(models.Model):
    """
    An OrderFee object represents a fee that is added to the order total independently of
    the actual positions. This might for example be a payment or a shipping fee.

    The default ``OrderFee.objects`` manager only contains fees that are not ``canceled``. If
    you ant all objects, you need to use ``OrderFee.all`` instead.

    :param value: Gross price of this fee
    :type value: Decimal
    :param order: Order this fee is charged with
    :type order: Order
    :param fee_type: The type of the fee, currently ``payment``, ``shipping``, ``service``, ``giftcard``, or ``other``.
    :type fee_type: str
    :param description: A human-readable description of the fee
    :type description: str
    :param internal_type: An internal string to group fees by, e.g. the identifier string of a payment provider
    :type internal_type: str
    :param tax_rate: The tax rate applied to this fee
    :type tax_rate: Decimal
    :param tax_rule: The tax rule applied to this fee
    :type tax_rule: TaxRule
    :param tax_value: The tax amount included in the price
    :type tax_value: Decimal
    :param canceled: True, if this position is canceled and should no longer be regarded
    :type canceled: bool
    """
    FEE_TYPE_PAYMENT = "payment"
    FEE_TYPE_SHIPPING = "shipping"
    FEE_TYPE_SERVICE = "service"
    FEE_TYPE_CANCELLATION = "cancellation"
    FEE_TYPE_INSURANCE = "insurance"
    FEE_TYPE_OTHER = "other"
    FEE_TYPE_GIFTCARD = "giftcard"
    FEE_TYPES = (
        (FEE_TYPE_PAYMENT, _("Payment fee")),
        (FEE_TYPE_SHIPPING, _("Shipping fee")),
        (FEE_TYPE_SERVICE, _("Service fee")),
        (FEE_TYPE_CANCELLATION, _("Cancellation fee")),
        (FEE_TYPE_INSURANCE, _("Insurance fee")),
        (FEE_TYPE_OTHER, _("Other fees")),
        (FEE_TYPE_GIFTCARD, _("Gift card")),
    )

    value = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Value")
    )
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='all_fees',
        on_delete=models.PROTECT
    )
    fee_type = models.CharField(
        max_length=100, choices=FEE_TYPES
    )
    description = models.CharField(max_length=190, blank=True)
    internal_type = models.CharField(max_length=255, blank=True)
    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name=_('Tax rate')
    )
    tax_rule = models.ForeignKey(
        'TaxRule',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    tax_value = models.DecimalField(
        max_digits=13, decimal_places=2,
        verbose_name=_('Tax value')
    )
    canceled = models.BooleanField(default=False)

    all = ScopedManager(organizer='order__event__organizer')
    objects = ActivePositionManager()

    @property
    def net_value(self):
        return self.value - self.tax_value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.get_deferred_fields():
            self._transaction_key_reset()

    def refresh_from_db(self, using=None, fields=None):
        """
        Reload field values from the database. Similar to django's implementation
        with adjustment for our method that forces us to create ``Transaction`` instances.
        """
        if not self.get_deferred_fields():
            self._transaction_key_reset()
        return super().refresh_from_db(using, fields)

    def _transaction_key_reset(self):
        self.__initial_transaction_key = Transaction.key(self)
        self.__initial_canceled = self.canceled

    def __str__(self):
        if self.description:
            return '{} - {}'.format(self.get_fee_type_display(), self.description)
        else:
            return self.get_fee_type_display()

    def __repr__(self):
        return '<OrderFee: type %s, value %d>' % (
            self.fee_type, self.value
        )

    def _calculate_tax(self, tax_rule=None):
        if tax_rule:
            self.tax_rule = tax_rule

        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None

        if not self.tax_rule and self.fee_type == "payment" and self.order.event.settings.tax_rate_default:
            self.tax_rule = self.order.event.settings.tax_rate_default

        if self.tax_rule:
            tax = self.tax_rule.tax(self.value, base_price_is='gross', invoice_address=ia, force_fixed_gross_price=True)
            self.tax_rate = tax.rate
            self.tax_value = tax.tax
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rule and not self.tax_rule.rate and not self.tax_rule.pk:
            self.tax_rule = None

        if self.tax_rate is None:
            self._calculate_tax()
        self.order.touch()

        if not self.get_deferred_fields():
            if Transaction.key(self) != self.__initial_transaction_key or self.canceled != self.__initial_canceled or not self.pk:
                _transactions_mark_order_dirty(self.order_id, using=kwargs.get('using', None))
        elif not kwargs.get('force_save_with_deferred_fields', None):
            _fail("It is unsafe to call save() on an OrderFee with deferred fields since we can't check if you missed "
                  "creating a transaction. Call save(force_save_with_deferred_fields=True) if you really want to do "
                  "this.")

        return super().save(*args, **kwargs)

    def delete(self, **kwargs):
        self.order.touch()
        super().delete(**kwargs)


class OrderPosition(AbstractPosition):
    """
    An OrderPosition is one line of an order, representing one ordered item
    of a specified type (or variation). This has all properties of
    AbstractPosition.

    The default ``OrderPosition.objects`` manager only contains fees that are not ``canceled``. If
    you want all objects, you need to use ``OrderPosition.all`` instead.

    :param order: The order this position is a part of
    :type order: Order
    :param positionid: A local ID of this position, counted for each order individually
    :type positionid: int
    :param tax_rate: The tax rate applied to this position
    :type tax_rate: Decimal
    :param tax_rule: The tax rule applied to this position
    :type tax_rule: TaxRule
    :param tax_value: The tax amount included in the price
    :type tax_value: Decimal
    :param secret: The secret used for ticket QR codes
    :type secret: str
    :param canceled: True, if this position is canceled and should no longer be regarded
    :type canceled: bool
    :param pseudonymization_id: The QR code content for lead scanning
    :type pseudonymization_id: str
    :param blocked: A list of reasons why this order position is blocked. Blocked positions can't be used for check-in and
                    other purposes. Each entry should be a short string that can be translated into a human-readable
                    description by a plugin. If the position is not blocked, the value must be ``None``, not an empty
                    list.
    :type blocked: list
    :param ignore_from_quota_while_blocked: Ignore this order position from quota, as long as ``blocked`` is set. Only
                                            to be used carefully by specific plugins.
    :type ignore_from_quota_while_blocked: boolean
    :param valid_from: The ticket will not be considered valid before this date. If the value is ``None``, no check on
                       ticket level is made.
    :type valid_from: datetime
    :param valid_until: The ticket will not be considered valid after this date. If the value is ``None``, no check on
                       ticket level is made.
    :type valid_until: datetime
    """
    positionid = models.PositiveIntegerField(default=1)

    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='all_positions',
        on_delete=models.PROTECT
    )

    voucher_budget_use = models.DecimalField(
        max_digits=13, decimal_places=2, null=True, blank=True,
    )

    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name=_('Tax rate')
    )
    tax_rule = models.ForeignKey(
        'TaxRule',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    tax_value = models.DecimalField(
        max_digits=13, decimal_places=2,
        verbose_name=_('Tax value')
    )

    secret = models.CharField(max_length=255, null=False, blank=False, db_index=True)
    web_secret = models.CharField(max_length=32, default=generate_secret, db_index=True)
    pseudonymization_id = models.CharField(
        max_length=16,
        unique=True,
        db_index=True
    )

    canceled = models.BooleanField(default=False)

    blocked = models.JSONField(null=True, blank=True)
    ignore_from_quota_while_blocked = models.BooleanField(default=False)
    valid_from = models.DateTimeField(
        verbose_name=_("Valid from"),
        null=True,
        blank=True,
    )
    valid_until = models.DateTimeField(
        verbose_name=_("Valid until"),
        null=True,
        blank=True,
    )

    all = ScopedManager(organizer='order__event__organizer')
    objects = ActivePositionManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.get_deferred_fields():
            self._transaction_key_reset()

    def refresh_from_db(self, using=None, fields=None):
        """
        Reload field values from the database. Similar to django's implementation
        with adjustment for our method that forces us to create ``Transaction`` instances.
        """
        if not self.get_deferred_fields():
            self._transaction_key_reset()
        return super().refresh_from_db(using, fields)

    def _transaction_key_reset(self):
        self.__initial_transaction_key = Transaction.key(self)
        self.__initial_canceled = self.canceled

    class Meta:
        verbose_name = _("Order position")
        verbose_name_plural = _("Order positions")
        ordering = ("positionid", "id")

    @cached_property
    def sort_key(self):
        return self.addon_to.positionid if self.addon_to else self.positionid, self.addon_to_id or 0, self.positionid

    @cached_property
    def require_checkin_attention(self):
        if self.order.checkin_attention or self.item.checkin_attention or (self.variation_id and self.variation.checkin_attention):
            return True
        return False

    @property
    def checkins(self):
        """
        Related manager for all successful checkins. Use ``all_checkins`` instead if you want
        canceled positions as well.
        """
        return self.all_checkins(manager='objects')

    @property
    def generate_ticket(self):
        if self.item.generate_tickets is not None:
            return self.item.generate_tickets
        if self.blocked:
            return False
        return (
            (self.order.event.settings.ticket_download_addons or not self.addon_to_id) and
            (self.event.settings.ticket_download_nonadm or self.item.admission)
        )

    @property
    def blocked_reasons(self):
        from ..signals import orderposition_blocked_display

        if not self.blocked:
            return []

        reasons = {}
        for b in self.blocked:
            for recv, response in orderposition_blocked_display.send(self.event, orderposition=self, block_name=b):
                if response:
                    reasons[b] = response
                    break
            else:
                reasons[b] = b
        return reasons

    @classmethod
    def transform_cart_positions(cls, cp: List, order) -> list:
        from . import Voucher

        ops = []
        cp_mapping = {}
        # The sorting key ensures that all addons come directly after the position they refer to
        for i, cartpos in enumerate(sorted(cp, key=lambda c: c.sort_key)):
            op = OrderPosition(order=order)
            for f in AbstractPosition._meta.fields:
                if f.name == 'addon_to':
                    setattr(op, f.name, cp_mapping.get(cartpos.addon_to_id))
                else:
                    setattr(op, f.name, getattr(cartpos, f.name))
            op._calculate_tax()
            if cartpos.voucher:
                op.voucher_budget_use = cartpos.listed_price - cartpos.price_after_voucher

            if cartpos.item.validity_mode:
                valid_from, valid_until = cartpos.item.compute_validity(
                    requested_start=(
                        max(cartpos.requested_valid_from, now())
                        if cartpos.requested_valid_from and cartpos.item.validity_dynamic_start_choice
                        else now()
                    ),
                    enforce_start_limit=True,
                    override_tz=order.event.timezone,
                )
                op.valid_from = valid_from
                op.valid_until = valid_until

            op.positionid = i + 1
            op.save()
            ops.append(op)
            cp_mapping[cartpos.pk] = op
            for answ in cartpos.answers.all():
                answ.orderposition = op
                answ.cartposition = None
                answ.save()
            if cartpos.voucher:
                Voucher.objects.filter(pk=cartpos.voucher.pk).update(redeemed=F('redeemed') + 1)
                cartpos.voucher.log_action('pretix.voucher.redeemed', {
                    'order_code': order.code
                })

        # Delete afterwards. Deleting in between might cause deletion of things related to add-ons
        # due to the deletion cascade.
        for cartpos in cp:
            if cartpos.pk:
                cartpos.addons.all().delete()
                cartpos.delete()
        return ops

    def __str__(self):
        if self.variation:
            return '#{} – {} – {}'.format(
                self.positionid, str(self.item), str(self.variation)
            )
        return '#{} – {}'.format(self.positionid, str(self.item))

    def __repr__(self):
        return '<OrderPosition: item %d, variation %d for order %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.order_id
        )

    def _calculate_tax(self, tax_rule=None):
        self.tax_rule = tax_rule or self.item.tax_rule
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None
        if self.tax_rule:
            tax = self.tax_rule.tax(self.price, invoice_address=ia, base_price_is='gross', force_fixed_gross_price=True)
            self.tax_rate = tax.rate
            self.tax_value = tax.tax
            if tax.gross != self.price:
                raise ValueError('Invalid tax calculation')
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        from pretix.base.secrets import assign_ticket_secret

        if self.tax_rate is None:
            self._calculate_tax()

        self.order.touch()
        if not self.pk:
            while not self.secret or OrderPosition.all.filter(
                secret=self.secret, order__event__organizer_id=self.order.event.organizer_id
            ).exists():
                assign_ticket_secret(
                    event=self.order.event, position=self, force_invalidate=True, save=False
                )
                if 'update_fields' in kwargs:
                    kwargs['update_fields'] = {'secret'}.union(kwargs['update_fields'])

        if not self.blocked and self.blocked is not None:
            self.blocked = None
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'blocked'}.union(kwargs['update_fields'])
        elif self.blocked and (not isinstance(self.blocked, list) or any(not isinstance(b, str) for b in self.blocked)):
            raise TypeError("blocked needs to be a list of strings")

        if not self.pseudonymization_id:
            self.assign_pseudonymization_id()
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'pseudonymization_id'}.union(kwargs['update_fields'])

        if not self.get_deferred_fields():
            if Transaction.key(self) != self.__initial_transaction_key or self.canceled != self.__initial_canceled or not self.pk:
                _transactions_mark_order_dirty(self.order_id, using=kwargs.get('using', None))
        elif not kwargs.get('force_save_with_deferred_fields', None):
            _fail("It is unsafe to call save() on an OrderFee with deferred fields since we can't check if you missed "
                  "creating a transaction. Call save(force_save_with_deferred_fields=True) if you really want to do "
                  "this.")

        return super().save(*args, **kwargs)

    @scopes_disabled()
    def assign_pseudonymization_id(self):
        # This omits some character pairs completely because they are hard to read even on screens (1/I and O/0)
        # and includes only one of two characters for some pairs because they are sometimes hard to distinguish in
        # handwriting (2/Z, 4/A, 5/S, 6/G). This allows for better detection e.g. in incoming wire transfers that
        # might include OCR'd handwritten text
        charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
        while True:
            code = get_random_string(length=10, allowed_chars=charset)
            with scopes_disabled():
                if not OrderPosition.all.filter(pseudonymization_id=code).exists():
                    self.pseudonymization_id = code
                    return

    @property
    def event(self):
        return self.order.event

    def send_mail(self, subject: str, template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.event.order.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, invoices: list=None,
                  auth=None, attach_tickets=False, attach_ical=False, attach_other_files: list=None):
        """
        Sends an email to the attendee. Basically, this method does two things:

        * Call ``pretix.base.services.mail.mail`` with useful values for the ``event``, ``locale``, ``recipient`` and
          ``order`` parameters.

        * Create a ``LogEntry`` with the email contents.

        :param subject: Subject of the email
        :param template: LazyI18nString or template filename, see ``pretix.base.services.mail.mail`` for more details
        :param context: Dictionary to use for rendering the template
        :param log_entry_type: Key to be used for the log entry
        :param user: Administrative user who triggered this mail to be sent
        :param headers: Dictionary with additional mail headers
        :param sender: Custom email sender.
        :param attach_tickets: Attach tickets of this order, if they are existing and ready to download
        :param attach_ical: Attach relevant ICS files
        """
        from pretix.base.services.mail import (
            SendMailException, mail, render_mail,
        )

        if not self.attendee_email:
            return

        for k, v in self.event.meta_data.items():
            context['meta_' + k] = v

        with language(self.order.locale, self.order.event.settings.region):
            recipient = self.attendee_email
            try:
                email_content = render_mail(template, context)
                subject = format_map(subject, context)
                mail(
                    recipient, subject, template, context,
                    self.event, self.order.locale, order=self.order, headers=headers, sender=sender,
                    position=self,
                    invoices=invoices,
                    attach_tickets=attach_tickets,
                    attach_ical=attach_ical,
                    attach_other_files=attach_other_files,
                )
            except SendMailException:
                raise
            else:
                self.order.log_action(
                    log_entry_type,
                    user=user,
                    auth=auth,
                    data={
                        'subject': subject,
                        'message': email_content,
                        'recipient': recipient,
                        'invoices': [i.pk for i in invoices] if invoices else [],
                        'attach_tickets': attach_tickets,
                        'attach_ical': attach_ical,
                    }
                )

    def resend_link(self, user=None, auth=None):

        with language(self.order.locale, self.order.event.settings.region):
            email_template = self.event.settings.mail_text_resend_link
            email_context = get_email_context(event=self.order.event, order=self.order, position=self)
            email_subject = self.event.settings.mail_subject_resend_link
            self.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.resend', user=user, auth=auth,
                attach_tickets=True
            )

    @property
    @scopes_disabled()
    def attendee_change_allowed(self) -> bool:
        """
        Returns whether or not this order can be changed by the attendee.
        """
        from .items import ItemAddOn

        if not self.event.settings.change_allow_attendee or not self.order.user_change_allowed:
            return False

        positions = list(
            self.order.positions.filter(Q(pk=self.pk) | Q(addon_to_id=self.pk)).annotate(
                has_variations=Exists(ItemVariation.objects.filter(item_id=OuterRef('item_id'))),
            ).select_related('item').prefetch_related('issued_gift_cards')
        )
        return (
            (self.order.event.settings.change_allow_user_variation and any([op.has_variations for op in positions])) or
            (self.order.event.settings.change_allow_user_addons and ItemAddOn.objects.filter(base_item_id__in=[op.item_id for op in positions]).exists())
        )


class Transaction(models.Model):
    """
    Transactions are a data structure that is redundant on the first sight but makes it possible to create good
    financial reporting.

    To understand this, think of "orders" as something like a contractual relationship between the organizer and the
    customer which requires to customer to pay some money and the organizer to provide a ticket.

    The ``Order``, ``OrderPosition``, and ``OrderFee`` models combined give a representation of the current contractual
    status of this relationship, i.e. how much and what is owed. The ``OrderPayment`` and ``OrderRefund`` models indicate
    the "other side" of the relationship, i.e. how much of the financial obligation has been met so far.

    However, while ``OrderPayment`` and ``OrderRefund`` objects are "final" and no longer change once they reached their
    final state, ``Order``, ``OrderPosition`` and ``OrderFee`` are highly mutable and can change at any time, e.g. if
    the customer moves their booking to a different day or a discount is applied retroactively.

    Therefore those models can be used to answer the question "how many tickets of type X have been sold for my event
    as of today?" but they cannot accurately answer the question "how many tickets of type X have been sold for my event
    as of last month?" because they lack this kind of historical information.

    Transactions help here because they are "immutable copies" or "modification records" of call positions and fees
    at the time of their creation and change. They only record data that is usually relevant for financial reporting,
    such as amounts, prices, products and dates involved. They do not record data like attendee names etc.

    Even before the introduction of the Transaction Model pretix *did* store historical data for auditability in the
    LogEntry model. However, it's almost impossible to do efficient reporting on that data.

    Transactions should never be generated manually but only through the ``order.create_transactions()``
    method which should be called **within the same database transaction**.

    The big downside of this approach is that you need to remember to update transaction records every time you change
    or create orders in new code paths. The mechanism introduced in ``pretix.base.models._transactions`` as well as
    the ``save()`` methods of ``Order``, ``OrderPosition`` and ``OrderFee`` intends to help you notice if you missed
    it. The only thing this *doesn't* catch is usage of ``OrderPosition.objects.bulk_create`` (and likewise for
    ``bulk_update`` and ``OrderFee``).

    :param id: ID of the transaction
    :param order: Order the transaction belongs to
    :param datetime: Date and time of the transaction
    :param migrated: Whether this object was reconstructed because the order was created before transactions where introduced
    :param positionid: Affected Position ID, in case this transaction represents a change in an order position
    :param count: An amount, multiplicator for price etc. For order positions this can *currently* only be -1 or +1, for
                  fees it can also be more in special cases
    :param item: ``Item``, in case this transaction represents a change in an order position
    :param variation: ``ItemVariation``, in case this transaction represents a change in an order position
    :param subevent: ``subevent``, in case this transaction represents a change in an order position
    :param price: Price of the changed position
    :param tax_rate: Tax rate of the changed position
    :param tax_rule: Used tax rule
    :param tax_value: Tax value in event currency
    :param fee_type: Fee type code in case this transaction represents a change in an order fee
    :param internal_type: Internal fee type in case this transaction represents a change in an order fee
    """
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='transactions',
        on_delete=models.PROTECT
    )
    created = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    datetime = models.DateTimeField(
        verbose_name=_("Date"),
    )
    migrated = models.BooleanField(
        default=False
    )
    positionid = models.PositiveIntegerField(default=1, null=True, blank=True)
    count = models.IntegerField(
        default=1
    )
    item = models.ForeignKey(
        Item,
        null=True, blank=True,
        verbose_name=_("Item"),
        on_delete=models.PROTECT
    )
    variation = models.ForeignKey(
        ItemVariation,
        null=True, blank=True,
        verbose_name=_("Variation"),
        on_delete=models.PROTECT
    )
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.PROTECT,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    price = models.DecimalField(
        decimal_places=2, max_digits=13,
        verbose_name=_("Price")
    )
    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name=_('Tax rate')
    )
    tax_rule = models.ForeignKey(
        'TaxRule',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    tax_value = models.DecimalField(
        max_digits=13, decimal_places=2,
        verbose_name=_('Tax value')
    )
    fee_type = models.CharField(
        max_length=100, choices=OrderFee.FEE_TYPES, null=True, blank=True
    )
    internal_type = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = 'datetime', 'pk'
        index_together = [
            ['datetime', 'id']
        ]

    def save(self, *args, **kwargs):
        if not self.fee_type and not self.item:
            raise ValidationError('Should set either item or fee type')
        return super().save(*args, **kwargs)

    @staticmethod
    def key(obj):
        if isinstance(obj, Transaction):
            return (obj.positionid, obj.item_id, obj.variation_id, obj.subevent_id, obj.price, obj.tax_rate,
                    obj.tax_rule_id, obj.tax_value, obj.fee_type, obj.internal_type)
        elif isinstance(obj, OrderPosition):
            return (obj.positionid, obj.item_id, obj.variation_id, obj.subevent_id, obj.price, obj.tax_rate,
                    obj.tax_rule_id, obj.tax_value, None, None)
        elif isinstance(obj, OrderFee):
            return (None, None, None, None, obj.value, obj.tax_rate,
                    obj.tax_rule_id, obj.tax_value, obj.fee_type, obj.internal_type)
        raise ValueError('invalid state')  # noqa

    @property
    def full_price(self):
        return self.price * self.count

    @property
    def full_tax_value(self):
        return self.tax_value * self.count


class CartPosition(AbstractPosition):
    """
    A cart position is similar to an order line, except that it is not
    yet part of a binding order but just placed by some user in his or
    her cart. It therefore normally has a much shorter expiration time
    than an ordered position, but still blocks an item in the quota pool
    as we do not want to throw out users while they're clicking through
    the checkout process. This has all properties of AbstractPosition.

    :param event: The event this belongs to
    :type event: Event
    :param cart_id: The user session that contains this cart position
    :type cart_id: str
    """
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        on_delete=models.CASCADE
    )
    cart_id = models.CharField(
        max_length=255, null=True, blank=True, db_index=True,
        verbose_name=_("Cart ID (e.g. session key)")
    )
    datetime = models.DateTimeField(
        verbose_name=_("Date"),
        auto_now_add=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date"),
        db_index=True
    )

    tax_rate = models.DecimalField(
        max_digits=7, decimal_places=2, default=Decimal('0.00'),
        verbose_name=_('Tax rate')
    )
    listed_price = models.DecimalField(
        decimal_places=2, max_digits=13, null=True,
    )
    price_after_voucher = models.DecimalField(
        decimal_places=2, max_digits=13, null=True,
    )
    custom_price_input = models.DecimalField(
        decimal_places=2, max_digits=13, null=True,
    )
    custom_price_input_is_net = models.BooleanField(
        default=False,
    )
    line_price_gross = models.DecimalField(
        decimal_places=2, max_digits=13, null=True,
    )
    requested_valid_from = models.DateTimeField(
        null=True,
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Cart position")
        verbose_name_plural = _("Cart positions")

    def __repr__(self):
        return '<CartPosition: item %d, variation %d for cart %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.cart_id
        )

    @property
    def tax_value(self):
        net = round_decimal(self.price - (self.price * (1 - 100 / (100 + self.tax_rate))),
                            self.event.currency)
        return self.price - net

    @cached_property
    def sort_key(self):
        subevent_key = (self.subevent.date_from, str(self.subevent.name), self.subevent_id) if self.subevent_id else (0, "", 0)
        category_key = (self.item.category.position, self.item.category.id) if self.item.category_id is not None else (0, 0)
        item_key = self.item.position, self.item_id
        variation_key = (self.variation.position, self.variation.id) if self.variation_id is not None else (0, 0)
        line_key = (self.price, (self.voucher_id or 0), (self.seat.sorting_rank if self.seat_id else 0), self.pk)
        sort_key = subevent_key + category_key + item_key + variation_key + line_key

        if self.addon_to_id:
            return self.addon_to.sort_key + (1 if self.is_bundled else 2,) + sort_key
        else:
            return sort_key

    def update_listed_price_and_voucher(self, voucher_only=False, max_discount=None):
        from pretix.base.services.pricing import (
            get_listed_price, is_included_for_free,
        )

        if voucher_only:
            listed_price = self.listed_price
        else:
            if self.addon_to_id and is_included_for_free(self.item, self.addon_to):
                listed_price = Decimal('0.00')
            else:
                listed_price = get_listed_price(self.item, self.variation, self.subevent)

        if self.voucher:
            price_after_voucher = self.voucher.calculate_price(listed_price, max_discount)
        else:
            price_after_voucher = listed_price

        if self.is_bundled:
            bundle = self.addon_to.item.bundles.filter(bundled_item=self.item, bundled_variation=self.variation).first()
            if bundle:
                if self.addon_to.voucher_id and self.addon_to.voucher.all_bundles_included:
                    listed_price = Decimal('0.00')
                    price_after_voucher = Decimal('0.00')
                else:
                    listed_price = bundle.designated_price
                    price_after_voucher = bundle.designated_price

        if listed_price != self.listed_price or price_after_voucher != self.price_after_voucher:
            self.listed_price = listed_price
            self.price_after_voucher = price_after_voucher
            self.save(update_fields=['listed_price', 'price_after_voucher'])

    def migrate_free_price_if_necessary(self):
        # Migrate from pre-discounts position
        if self.item.free_price and self.custom_price_input is None:
            custom_price = self.price
            if custom_price > 99_999_999_999:
                raise ValueError('price_too_high')
            self.custom_price_input = custom_price
            self.custom_price_input_is_net = not False
            self.save(update_fields=['custom_price_input', 'custom_price_input_is_net'])

    def update_line_price(self, invoice_address, bundled_positions):
        from pretix.base.services.pricing import get_line_price

        line_price = get_line_price(
            price_after_voucher=self.price_after_voucher,
            custom_price_input=self.custom_price_input,
            custom_price_input_is_net=self.custom_price_input_is_net,
            tax_rule=self.item.tax_rule,
            invoice_address=invoice_address,
            bundled_sum=sum([b.price_after_voucher for b in bundled_positions]),
            is_bundled=self.is_bundled,
        )
        if line_price.gross != self.line_price_gross or line_price.rate != self.tax_rate:
            self.line_price_gross = line_price.gross
            self.tax_rate = line_price.rate
            self.save(update_fields=['line_price_gross', 'tax_rate'])

    @property
    def addons_without_bundled(self):
        addons = [op for op in self.addons.all() if not op.is_bundled]
        return sorted(addons, key=lambda cp: cp.sort_key)

    @cached_property
    def predicted_validity(self):
        return self.item.compute_validity(
            requested_start=(
                max(self.requested_valid_from, now())
                if self.requested_valid_from and self.item.validity_dynamic_start_choice
                else now()
            ),
            override_tz=self.event.timezone,
        )

    @property
    def valid_from(self):
        return self.predicted_validity[0]

    @property
    def valid_until(self):
        return self.predicted_validity[1]


class InvoiceAddress(models.Model):
    last_modified = models.DateTimeField(auto_now=True)
    order = models.OneToOneField(Order, null=True, blank=True, related_name='invoice_address', on_delete=models.CASCADE)
    customer = models.ForeignKey(
        Customer,
        related_name='invoice_addresses',
        null=True, blank=True,
        on_delete=models.CASCADE
    )
    is_business = models.BooleanField(default=False, verbose_name=_('Business customer'))
    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'))
    name_cached = models.CharField(max_length=255, verbose_name=_('Full name'), blank=True)
    name_parts = models.JSONField(default=dict)
    street = models.TextField(verbose_name=_('Address'), blank=False)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=False)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=False)
    country_old = models.CharField(max_length=255, verbose_name=_('Country'), blank=False)
    country = FastCountryField(verbose_name=_('Country'), blank=False, blank_label=_('Select country'),
                               countries=CachedCountries)
    state = models.CharField(max_length=255, verbose_name=pgettext_lazy('address', 'State'), blank=True)
    vat_id = models.CharField(max_length=255, blank=True, verbose_name=_('VAT ID'))
    vat_id_validated = models.BooleanField(default=False)
    custom_field = models.CharField(max_length=255, null=True, blank=True)
    internal_reference = models.TextField(
        verbose_name=_('Internal reference'),
        help_text=_('This reference will be printed on your invoice for your convenience.'),
        blank=True,
    )
    beneficiary = models.TextField(
        verbose_name=_('Beneficiary'),
        blank=True
    )

    objects = ScopedManager(organizer='order__event__organizer')
    profiles = ScopedManager(organizer='customer__organizer')

    def save(self, **kwargs):
        if self.order:
            self.order.touch()

        if self.name_parts:
            name = self.name
            if self.name_cached != name:
                self.name_cached = self.name
                if 'update_fields' in kwargs:
                    kwargs['update_fields'] = {'name_cached'}.union(kwargs['update_fields'])
        else:
            if self.name_cached != "" or self.name_parts != {}:
                self.name_cached = ""
                self.name_parts = {}
                if 'update_fields' in kwargs:
                    kwargs['update_fields'] = {'name_cached', 'name_parts'}.union(kwargs['update_fields'])
        super().save(**kwargs)

    def describe(self):
        parts = [
            self.company,
            self.name,
            self.street,
            (self.zipcode or '') + ' ' + (self.city or '') + ' ' + (self.state_for_address or ''),
            self.country.name,
            self.vat_id,
            self.custom_field,
            self.internal_reference,
            (_('Beneficiary') + ': ' + self.beneficiary) if self.beneficiary else '',
        ]
        return '\n'.join([str(p).strip() for p in parts if p and str(p).strip()])

    @property
    def is_empty(self):
        return (
            not self.name_cached and not self.company and not self.street and not self.zipcode and not self.city
            and not self.internal_reference and not self.beneficiary
        )

    @property
    def state_name(self):
        sd = pycountry.subdivisions.get(code='{}-{}'.format(self.country, self.state))
        if sd:
            return sd.name
        return self.state

    @property
    def state_for_address(self):
        from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS
        if not self.state or str(self.country) not in COUNTRIES_WITH_STATE_IN_ADDRESS:
            return ""
        if COUNTRIES_WITH_STATE_IN_ADDRESS[str(self.country)][1] == 'long':
            return self.state_name
        return self.state

    @property
    def name(self):
        return build_name(self.name_parts, fallback_scheme=lambda: self.order.event.settings.name_scheme) or ""

    @property
    def name_all_components(self):
        return build_name(self.name_parts, "concatenation_all_components", fallback_scheme=lambda: self.order.event.settings.name_scheme) or ""

    def for_js(self):
        d = {}

        if self.name_parts:
            if '_scheme' in self.name_parts:
                scheme = PERSON_NAME_SCHEMES[self.name_parts['_scheme']]
                for i, (k, l, w) in enumerate(scheme['fields']):
                    d[f'name_parts_{i}'] = self.name_parts.get(k) or ''

        d.update({
            'company': self.company,
            'is_business': self.is_business,
            'street': self.street,
            'zipcode': self.zipcode,
            'city': self.city,
            'country': str(self.country) if self.country else None,
            'state': str(self.state) if self.state else None,
            'vat_id': self.vat_id,
            'custom_field': self.custom_field,
            'internal_reference': self.internal_reference,
            'beneficiary': self.beneficiary,
        })
        return d


def cachedticket_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'tickets/{org}/{ev}/{code}-{no}-{prov}-{secret}.dat'.format(
        org=instance.order_position.order.event.organizer.slug,
        ev=instance.order_position.order.event.slug,
        prov=instance.provider,
        no=instance.order_position.positionid,
        code=instance.order_position.order.code,
        secret=secret,
    )


def cachedcombinedticket_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'tickets/{org}/{ev}/{code}-{prov}-{secret}.dat'.format(
        org=instance.order.event.organizer.slug,
        ev=instance.order.event.slug,
        prov=instance.provider,
        code=instance.order.code,
        secret=secret
    )


class CachedTicket(models.Model):
    order_position = models.ForeignKey(OrderPosition, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    extension = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedticket_name, max_length=255)
    created = models.DateTimeField(auto_now_add=True)


class CachedCombinedTicket(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    provider = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    extension = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedcombinedticket_name, max_length=255)
    created = models.DateTimeField(auto_now_add=True)


class CancellationRequest(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='cancellation_requests')
    created = models.DateTimeField(auto_now_add=True)
    cancellation_fee = models.DecimalField(max_digits=13, decimal_places=2)
    refund_as_giftcard = models.BooleanField(default=False)


class RevokedTicketSecret(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='revoked_secrets')
    position = models.ForeignKey(
        OrderPosition,
        on_delete=models.SET_NULL,
        related_name='revoked_secrets',
        null=True,
    )
    secret = models.TextField(db_index=True)
    created = models.DateTimeField(auto_now_add=True)


class BlockedTicketSecret(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='blocked_secrets')
    position = models.ForeignKey(
        OrderPosition,
        on_delete=models.SET_NULL,
        related_name='blocked_secrets',
        null=True,
    )
    secret = models.TextField(db_index=True)
    blocked = models.BooleanField()
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('event', 'secret'),)


@receiver(post_delete, sender=CachedTicket)
def cachedticket_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)


@receiver(post_delete, sender=CachedCombinedTicket)
def cachedcombinedticket_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)


@receiver(post_delete, sender=QuestionAnswer)
def answer_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)
