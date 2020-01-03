import copy
import hashlib
import json
import logging
import os
import string
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Union

import dateutil
import pycountry
import pytz
from django.conf import settings
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
from django.utils.timezone import make_aware, now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_countries.fields import Country, CountryField
from django_scopes import ScopedManager, scopes_disabled
from i18nfield.strings import LazyI18nString
from jsonfallback.fields import FallbackJSONField
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers import NumberParseException

from pretix.base.banlist import banned
from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import User
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.services.locking import NoLockManager
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import order_gracefully_delete

from .base import LockModel, LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation, Question, QuestionOption, Quota

logger = logging.getLogger(__name__)


def generate_secret():
    return get_random_string(length=16, allowed_chars=string.ascii_lowercase + string.digits)


def generate_position_secret():
    # Exclude o,0,1,i,l to avoid confusion with bad fonts/printers
    return get_random_string(length=settings.ENTROPY['ticket_secret'], allowed_chars='abcdefghjkmnpqrstuvwxyz23456789')


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

    :param event: The event this order belongs to
    :type event: Event
    :param email: The email of the person who ordered this
    :type email: str
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
    testmode = models.BooleanField(default=False)
    event = models.ForeignKey(
        Event,
        verbose_name=_("Event"),
        related_name="orders",
        on_delete=models.CASCADE
    )
    email = models.EmailField(
        null=True, blank=True,
        verbose_name=_('E-mail')
    )
    locale = models.CharField(
        null=True, blank=True, max_length=32,
        verbose_name=_('Locale')
    )
    secret = models.CharField(max_length=32, default=generate_secret)
    datetime = models.DateTimeField(
        verbose_name=_("Date"), db_index=True
    )
    expires = models.DateTimeField(
        verbose_name=_("Expiration date")
    )
    total = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Total amount")
    )
    comment = models.TextField(
        blank=True, verbose_name=_("Comment"),
        help_text=_("The text entered in this field will not be visible to the user and is available for your "
                    "convenience.")
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
        auto_now=True, db_index=True
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
        ordering = ("-datetime",)

    def __str__(self):
        return self.full_code

    def gracefully_delete(self, user=None, auth=None):
        from . import Voucher, GiftCard, GiftCardTransaction

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
        OrderPosition.all.filter(order=self, addon_to__isnull=False).delete()
        OrderPosition.all.filter(order=self).delete()
        OrderFee.all.filter(order=self).delete()
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
        payment_sum_sq = Subquery(payment_sum, output_field=models.DecimalField(decimal_places=2, max_digits=10))
        refund_sum_sq = Subquery(refund_sum, output_field=models.DecimalField(decimal_places=2, max_digits=10))
        if sums:
            qs = qs.annotate(
                payment_sum=payment_sum_sq,
                refund_sum=refund_sum_sq,
            )

        qs = qs.annotate(
            pending_sum_t=F('total') - Coalesce(payment_sum_sq, 0) + Coalesce(refund_sum_sq, 0),
            pending_sum_rc=-1 * Coalesce(payment_sum_sq, 0) + Coalesce(refund_sum_sq, 0),
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
                         then=Value('1')),
                    When(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=-1e-8),
                         then=Value('1')),
                    default=Value('0'),
                    output_field=models.IntegerField()
                ),
                is_pending_with_full_payment=Case(
                    When(Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=1e-8)
                         & Q(require_approval=False),
                         then=Value('1')),
                    default=Value('0'),
                    output_field=models.IntegerField()
                ),
                is_underpaid=Case(
                    When(Q(status=Order.STATUS_PAID) & Q(pending_sum_t__gt=1e-8),
                         then=Value('1')),
                    default=Value('0'),
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

    @property
    def changable(self):
        return self.status in (Order.STATUS_PAID, Order.STATUS_PENDING)

    def save(self, **kwargs):
        if 'update_fields' in kwargs and 'last_modified' not in kwargs['update_fields']:
            kwargs['update_fields'] = list(kwargs['update_fields']) + ['last_modified']
        if not self.code:
            self.assign_code()
        if not self.datetime:
            self.datetime = now()
        if not self.expires:
            self.set_expires()
        super().save(**kwargs)

    def touch(self):
        self.save(update_fields=['last_modified'])

    def set_expires(self, now_dt=None, subevents=None):
        now_dt = now_dt or now()
        tz = pytz.timezone(self.event.settings.timezone)
        exp_by_date = now_dt.astimezone(tz) + timedelta(days=self.event.settings.get('payment_term_days', as_type=int))
        exp_by_date = exp_by_date.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=0)
        if self.event.settings.get('payment_term_weekdays'):
            if exp_by_date.weekday() == 5:
                exp_by_date += timedelta(days=2)
            elif exp_by_date.weekday() == 6:
                exp_by_date += timedelta(days=1)

        self.expires = exp_by_date

        term_last = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if term_last:
            if self.event.has_subevents and subevents:
                term_last = min([
                    term_last.datetime(se).date()
                    for se in subevents
                ])
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
            self.status in (Order.STATUS_PENDING, Order.STATUS_PAID) and self.count_positions
        )

    @cached_property
    def user_cancel_deadline(self):
        if self.status == Order.STATUS_PAID and self.total != Decimal('0.00'):
            until = self.event.settings.get('cancel_allow_user_paid_until', as_type=RelativeDateWrapper)
        else:
            until = self.event.settings.get('cancel_allow_user_until', as_type=RelativeDateWrapper)
        if until:
            if self.event.has_subevents:
                return min([
                    until.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ])
            else:
                return until.datetime(self.event)

    @cached_property
    def user_cancel_fee(self):
        fee = Decimal('0.00')
        if self.event.settings.cancel_allow_user_paid_keep:
            fee += self.event.settings.cancel_allow_user_paid_keep
        if self.event.settings.cancel_allow_user_paid_keep_percentage:
            fee += self.event.settings.cancel_allow_user_paid_keep_percentage / Decimal('100.0') * self.total
        if self.event.settings.cancel_allow_user_paid_keep_fees:
            fee += self.fees.filter(
                fee_type__in=(OrderFee.FEE_TYPE_PAYMENT, OrderFee.FEE_TYPE_SHIPPING, OrderFee.FEE_TYPE_SERVICE)
            ).aggregate(
                s=Sum('value')
            )['s'] or 0
        return round_decimal(fee, self.event.currency)

    @property
    @scopes_disabled()
    def user_cancel_allowed(self) -> bool:
        """
        Returns whether or not this order can be canceled by the user.
        """
        from .checkin import Checkin

        positions = list(
            self.positions.all().annotate(
                has_checkin=Exists(Checkin.objects.filter(position_id=OuterRef('pk')))
            ).select_related('item').prefetch_related('issued_gift_cards')
        )
        cancelable = all([op.item.allow_cancel and not op.has_checkin for op in positions])
        if not cancelable or not positions:
            return False
        for op in positions:
            for gc in op.issued_gift_cards.all():
                if gc.value != op.price:
                    return False
        if self.user_cancel_deadline and now() > self.user_cancel_deadline:
            return False
        if self.status == Order.STATUS_PENDING:
            return self.event.settings.cancel_allow_user
        elif self.status == Order.STATUS_PAID:
            if self.total == Decimal('0.00'):
                return self.event.settings.cancel_allow_user
            return self.event.settings.cancel_allow_user_paid
        return False

    def propose_auto_refunds(self, amount: Decimal, payments: list=None):
        # Algorithm to choose which payments are to be refunded to create the least hassle
        payments = payments or self.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED)
        for p in payments:
            p.full_refund_possible = p.payment_provider.payment_refund_supported(p)
            p.partial_refund_possible = p.payment_provider.payment_partial_refund_supported(p)
            p.propose_refund = Decimal('0.00')
            p.available_amount = p.amount - p.refunded_amount

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
    def normalize_code(code):
        tr = str.maketrans({
            '2': 'Z',
            '4': 'A',
            '5': 'S',
            '6': 'G',
        })
        return code.upper().translate(tr)

    def assign_code(self):
        # This omits some character pairs completely because they are hard to read even on screens (1/I and O/0)
        # and includes only one of two characters for some pairs because they are sometimes hard to distinguish in
        # handwriting (2/Z, 4/A, 5/S, 6/G). This allows for better detection e.g. in incoming wire transfers that
        # might include OCR'd handwritten text
        charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
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
                # Safeguard: If we don't find an unused and non-blacklisted code within 20 iterations, we increase
                # the length.
                length += 1
                iteration = 0

    @property
    def can_modify_answers(self) -> bool:
        """
        ``True`` if the user can change the question answers / attendee names that are
        related to the order. This checks order status and modification deadlines. It also
        returns ``False`` if there are no questions that can be answered.
        """
        if self.status not in (Order.STATUS_PENDING, Order.STATUS_PAID, Order.STATUS_EXPIRED):
            return False

        modify_deadline = self.event.settings.get('last_order_modification_date', as_type=RelativeDateWrapper)
        if self.event.has_subevents and modify_deadline:
            modify_deadline = min([
                modify_deadline.datetime(se)
                for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
            ])
        elif modify_deadline:
            modify_deadline = modify_deadline.datetime(self.event)

        if modify_deadline is not None and now() > modify_deadline:
            return False
        if self.event.settings.get('invoice_address_asked', as_type=bool):
            return True
        ask_names = self.event.settings.get('attendee_names_asked', as_type=bool)
        for cp in self.positions.all().prefetch_related('item__questions'):
            if (cp.item.admission and ask_names) or cp.item.questions.all():
                return True

        return False  # nothing there to modify

    @property
    def is_expired_by_time(self):
        return (
            self.status == Order.STATUS_PENDING and self.expires < now()
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
                dl_date = min([
                    dl_date.datetime(se)
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ])
            else:
                dl_date = dl_date.datetime(self.event)
        return dl_date

    @property
    def ticket_download_available(self):
        return self.event.settings.ticket_download and (
            self.event.settings.ticket_download_date is None
            or now() > self.ticket_download_date
        ) and (
            self.status == Order.STATUS_PAID
            or (
                (self.event.settings.ticket_download_pending or self.total == Decimal("0.00")) and
                self.status == Order.STATUS_PENDING and
                not self.require_approval
            )
        )

    @property
    def payment_term_last(self):
        tz = pytz.timezone(self.event.settings.timezone)
        term_last = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if term_last:
            if self.event.has_subevents:
                term_last = min([
                    term_last.datetime(se).date()
                    for se in self.event.subevents.filter(id__in=self.positions.values_list('subevent', flat=True))
                ])
            else:
                term_last = term_last.datetime(self.event).date()
            term_last = make_aware(datetime.combine(
                term_last,
                time(hour=23, minute=59, second=59)
            ), tz)
        return term_last

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

    def _is_still_available(self, now_dt: datetime=None, count_waitinglist=True, force=False) -> Union[bool, str]:
        error_messages = {
            'unavailable': _('The ordered product "{item}" is no longer available.'),
            'seat_unavailable': _('The seat "{seat}" is no longer available.'),
            'voucher_budget': _('The voucher "{voucher}" no longer has sufficient budget.'),
        }
        now_dt = now_dt or now()
        positions = self.positions.all().select_related('item', 'variation', 'seat', 'voucher')
        quota_cache = {}
        v_budget = {}
        try:
            for i, op in enumerate(positions):
                if op.seat:
                    if not op.seat.is_available(ignore_orderpos=op):
                        raise Quota.QuotaExceededException(error_messages['seat_unavailable'].format(seat=op.seat))
                if force:
                    continue

                if op.voucher and op.voucher.budget is not None and op.price_before_voucher is not None:
                    if op.voucher not in v_budget:
                        v_budget[op.voucher] = op.voucher.budget - op.voucher.budget_used()
                    disc = op.price_before_voucher - op.price
                    if disc > v_budget[op.voucher]:
                        raise Quota.QuotaExceededException(error_messages['voucher_budget'].format(
                            voucher=op.voucher.code
                        ))
                    v_budget[op.voucher] -= disc

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

    def send_mail(self, subject: str, template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.event.order.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, invoices: list=None,
                  auth=None, attach_tickets=False, position: 'OrderPosition'=None, auto_email=True,
                  attach_ical=False):
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
        from pretix.base.services.mail import SendMailException, mail, render_mail

        if not self.email:
            return

        for k, v in self.event.meta_data.items():
            context['meta_' + k] = v

        with language(self.locale):
            recipient = self.email
            if position and position.attendee_email:
                recipient = position.attendee_email

            try:
                email_content = render_mail(template, context)
                mail(
                    recipient, subject, template, context,
                    self.event, self.locale, self, headers=headers, sender=sender,
                    invoices=invoices, attach_tickets=attach_tickets,
                    position=position, auto_email=auto_email, attach_ical=attach_ical
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
        with language(self.locale):
            email_template = self.event.settings.mail_text_resend_link
            email_context = get_email_context(event=self.event, order=self)
            email_subject = _('Your order: %(code)s') % {'code': self.code}
            self.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.resend', user=user, auth=auth,
                attach_tickets=True,
            )

    @property
    def positions_with_tickets(self):
        for op in self.positions.all():
            if not op.generate_ticket:
                continue
            yield op


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
        return any(self.file.name.endswith(e) for e in ('.jpg', '.png', '.gif', '.tiff', '.bmp', '.jpeg'))

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
                    tz = pytz.timezone(self.orderposition.order.event.settings.timezone)
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
    price_before_voucher = models.DecimalField(
        decimal_places=2, max_digits=10, null=True,
    )
    price = models.DecimalField(
        decimal_places=2, max_digits=10,
        verbose_name=_("Price")
    )
    attendee_name_cached = models.CharField(
        max_length=255,
        verbose_name=_("Attendee name"),
        blank=True, null=True,
        help_text=_("Empty, if this product is not an admission ticket")
    )
    attendee_name_parts = FallbackJSONField(
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

    class Meta:
        abstract = True

    @property
    def meta_info_data(self):
        if self.meta_info:
            return json.loads(self.meta_info)
        else:
            return {}

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
        for a in self.answers.all():
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
        self.attendee_name_cached = self.attendee_name
        if self.attendee_name_parts is None:
            self.attendee_name_parts = {}
        super().save(*args, **kwargs)

    @property
    def attendee_name(self):
        if not self.attendee_name_parts:
            return None
        if '_legacy' in self.attendee_name_parts:
            return self.attendee_name_parts['_legacy']
        if '_scheme' in self.attendee_name_parts:
            scheme = PERSON_NAME_SCHEMES[self.attendee_name_parts['_scheme']]
        else:
            scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme]
        return scheme['concatenation'](self.attendee_name_parts).strip()


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
        decimal_places=2, max_digits=10,
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
    def _mark_paid(self, force, count_waitinglist, user, auth, ignore_date=False, overpaid=False):
        from pretix.base.signals import order_paid
        can_be_paid = self.order._can_be_paid(count_waitinglist=count_waitinglist, ignore_date=ignore_date, force=force)
        if can_be_paid is not True:
            self.order.log_action('pretix.event.order.quotaexceeded', {
                'message': can_be_paid
            }, user=user, auth=auth)
            raise Quota.QuotaExceededException(can_be_paid)
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

    def confirm(self, count_waitinglist=True, send_mail=True, force=False, user=None, auth=None, mail_text='',
                ignore_date=False, lock=True, payment_date=None):
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
        from pretix.base.services.invoices import generate_invoice, invoice_qualified

        with transaction.atomic():
            locked_instance = OrderPayment.objects.select_for_update().get(pk=self.pk)
            if locked_instance.state == self.PAYMENT_STATE_CONFIRMED:
                # Race condition detected, this payment is already confirmed
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
            return

        payment_sum = self.order.payments.filter(
            state__in=(self.PAYMENT_STATE_CONFIRMED, self.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.order.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT,
                       OrderRefund.REFUND_STATE_CREATED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        if payment_sum - refund_sum < self.order.total:
            return

        if (self.order.status == Order.STATUS_PENDING and self.order.expires > now() + timedelta(hours=12)) or not lock:
            # Performance optimization. In this case, there's really no reason to lock everything and an atomic
            # database transaction is more than enough.
            lockfn = NoLockManager
        else:
            lockfn = self.order.event.lock

        with lockfn():
            self._mark_paid(force, count_waitinglist, user, auth, overpaid=payment_sum - refund_sum > self.order.total,
                            ignore_date=ignore_date)

        invoice = None
        if invoice_qualified(self.order):
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

        if send_mail:
            self._send_paid_mail(invoice, user, mail_text)
            if self.order.event.settings.mail_send_order_paid_attendee:
                for p in self.order.positions.all():
                    if p.addon_to_id is None and p.attendee_email and p.attendee_email != self.order.email:
                        self._send_paid_mail_attendee(p, user)

    def _send_paid_mail_attendee(self, position, user):
        from pretix.base.services.mail import SendMailException

        with language(self.order.locale):
            email_template = self.order.event.settings.mail_text_order_paid_attendee
            email_context = get_email_context(event=self.order.event, order=self.order, position=position)
            email_subject = _('Event registration confirmed: %(code)s') % {'code': self.order.code}
            try:
                self.order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_paid', user,
                    invoices=[], position=position,
                    attach_tickets=True,
                    attach_ical=self.order.event.settings.mail_attach_ical
                )
            except SendMailException:
                logger.exception('Order paid email could not be sent')

    def _send_paid_mail(self, invoice, user, mail_text):
        from pretix.base.services.mail import SendMailException

        with language(self.order.locale):
            email_template = self.order.event.settings.mail_text_order_paid
            email_context = get_email_context(event=self.order.event, order=self.order, payment_info=mail_text)
            email_subject = _('Payment received for your order: %(code)s') % {'code': self.order.code}
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
        decimal_places=2, max_digits=10,
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
        :param user: The API auth token that performed the change
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
    FEE_TYPE_OTHER = "other"
    FEE_TYPE_GIFTCARD = "giftcard"
    FEE_TYPES = (
        (FEE_TYPE_PAYMENT, _("Payment fee")),
        (FEE_TYPE_SHIPPING, _("Shipping fee")),
        (FEE_TYPE_SERVICE, _("Service fee")),
        (FEE_TYPE_CANCELLATION, _("Cancellation fee")),
        (FEE_TYPE_OTHER, _("Other fees")),
        (FEE_TYPE_GIFTCARD, _("Gift card")),
    )

    value = models.DecimalField(
        decimal_places=2, max_digits=10,
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
        max_digits=10, decimal_places=2,
        verbose_name=_('Tax value')
    )
    canceled = models.BooleanField(default=False)

    all = ScopedManager(organizer='order__event__organizer')
    objects = ActivePositionManager()

    @property
    def net_value(self):
        return self.value - self.tax_value

    def __str__(self):
        if self.description:
            return '{} - {}'.format(self.get_fee_type_display(), self.description)
        else:
            return self.get_fee_type_display()

    def __repr__(self):
        return '<OrderFee: type %s, value %d>' % (
            self.fee_type, self.value
        )

    def _calculate_tax(self):
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None

        if not self.tax_rule and self.fee_type == "payment" and self.order.event.settings.tax_rate_default:
            self.tax_rule = self.order.event.settings.tax_rate_default

        if self.tax_rule:
            if self.tax_rule.tax_applicable(ia):
                tax = self.tax_rule.tax(self.value, base_price_is='gross')
                self.tax_rate = tax.rate
                self.tax_value = tax.tax
            else:
                self.tax_value = Decimal('0.00')
                self.tax_rate = Decimal('0.00')
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rate is None:
            self._calculate_tax()
        self.order.touch()
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
    you ant all objects, you need to use ``OrderPosition.all`` instead.

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
    """
    positionid = models.PositiveIntegerField(default=1)
    order = models.ForeignKey(
        Order,
        verbose_name=_("Order"),
        related_name='all_positions',
        on_delete=models.PROTECT
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
        max_digits=10, decimal_places=2,
        verbose_name=_('Tax value')
    )
    secret = models.CharField(max_length=64, default=generate_position_secret, db_index=True)
    web_secret = models.CharField(max_length=32, default=generate_secret, db_index=True)
    pseudonymization_id = models.CharField(
        max_length=16,
        unique=True,
        db_index=True
    )
    canceled = models.BooleanField(default=False)

    all = ScopedManager(organizer='order__event__organizer')
    objects = ActivePositionManager()

    class Meta:
        verbose_name = _("Order position")
        verbose_name_plural = _("Order positions")
        ordering = ("positionid", "id")

    @cached_property
    def sort_key(self):
        return self.addon_to.positionid if self.addon_to else self.positionid, self.addon_to_id or 0

    @property
    def generate_ticket(self):
        if self.item.generate_tickets is not None:
            return self.item.generate_tickets
        return (
            (self.order.event.settings.ticket_download_addons or not self.addon_to_id) and
            (self.event.settings.ticket_download_nonadm or self.item.admission)
        )

    @classmethod
    def transform_cart_positions(cls, cp: List, order) -> list:
        from . import Voucher

        ops = []
        cp_mapping = {}
        # The sorting key ensures that all addons come directly after the position they refer to
        for i, cartpos in enumerate(sorted(cp, key=lambda c: (c.addon_to_id or c.pk, c.addon_to_id or 0))):
            op = OrderPosition(order=order)
            for f in AbstractPosition._meta.fields:
                if f.name == 'addon_to':
                    setattr(op, f.name, cp_mapping.get(cartpos.addon_to_id))
                else:
                    setattr(op, f.name, getattr(cartpos, f.name))
            op._calculate_tax()
            op.positionid = i + 1
            op.save()
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

    def _calculate_tax(self):
        self.tax_rule = self.item.tax_rule
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = None
        if self.tax_rule:
            if self.tax_rule.tax_applicable(ia):
                tax = self.tax_rule.tax(self.price, base_price_is='gross')
                self.tax_rate = tax.rate
                self.tax_value = tax.tax
            else:
                self.tax_value = Decimal('0.00')
                self.tax_rate = Decimal('0.00')
        else:
            self.tax_value = Decimal('0.00')
            self.tax_rate = Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.tax_rate is None:
            self._calculate_tax()
        self.order.touch()
        if self.pk is None:
            while OrderPosition.all.filter(secret=self.secret).exists():
                self.secret = generate_position_secret()

        if not self.pseudonymization_id:
            self.assign_pseudonymization_id()

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
            if not OrderPosition.all.filter(pseudonymization_id=code).exists():
                self.pseudonymization_id = code
                return

    @property
    def event(self):
        return self.order.event

    def send_mail(self, subject: str, template: Union[str, LazyI18nString],
                  context: Dict[str, Any]=None, log_entry_type: str='pretix.event.order.email.sent',
                  user: User=None, headers: dict=None, sender: str=None, invoices: list=None,
                  auth=None, attach_tickets=False):
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
        """
        from pretix.base.services.mail import SendMailException, mail, render_mail

        if not self.attendee_email:
            return

        for k, v in self.event.meta_data.items():
            context['meta_' + k] = v

        with language(self.order.locale):
            recipient = self.attendee_email
            try:
                email_content = render_mail(template, context)
                mail(
                    recipient, subject, template, context,
                    self.event, self.order.locale, order=self.order, headers=headers, sender=sender,
                    position=self,
                    invoices=invoices, attach_tickets=attach_tickets
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
                    }
                )

    def resend_link(self, user=None, auth=None):

        with language(self.order.locale):
            email_template = self.event.settings.mail_text_resend_link
            email_context = get_email_context(event=self.order.event, order=self.order, position=self)
            email_subject = _('Your event registration: %(code)s') % {'code': self.order.code}
            self.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.resend', user=user, auth=auth,
                attach_tickets=True
            )


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
    includes_tax = models.BooleanField(
        default=True
    )
    is_bundled = models.BooleanField(default=False)

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Cart position")
        verbose_name_plural = _("Cart positions")

    def __repr__(self):
        return '<CartPosition: item %d, variation %d for cart %s>' % (
            self.item.id, self.variation.id if self.variation else 0, self.cart_id
        )

    @property
    def tax_rate(self):
        if self.includes_tax:
            return self.item.tax(self.price, base_price_is='gross').rate
        else:
            return Decimal('0.00')

    @property
    def tax_value(self):
        if self.includes_tax:
            return self.item.tax(self.price, base_price_is='gross').tax
        else:
            return Decimal('0.00')


class InvoiceAddress(models.Model):
    last_modified = models.DateTimeField(auto_now=True)
    order = models.OneToOneField(Order, null=True, blank=True, related_name='invoice_address', on_delete=models.CASCADE)
    is_business = models.BooleanField(default=False, verbose_name=_('Business customer'))
    company = models.CharField(max_length=255, blank=True, verbose_name=_('Company name'))
    name_cached = models.CharField(max_length=255, verbose_name=_('Full name'), blank=True)
    name_parts = FallbackJSONField(default=dict)
    street = models.TextField(verbose_name=_('Address'), blank=False)
    zipcode = models.CharField(max_length=30, verbose_name=_('ZIP code'), blank=False)
    city = models.CharField(max_length=255, verbose_name=_('City'), blank=False)
    country_old = models.CharField(max_length=255, verbose_name=_('Country'), blank=False)
    country = CountryField(verbose_name=_('Country'), blank=False, blank_label=_('Select country'))
    state = models.CharField(max_length=255, verbose_name=pgettext_lazy('address', 'State'), blank=True)
    vat_id = models.CharField(max_length=255, blank=True, verbose_name=_('VAT ID'),
                              help_text=_('Only for business customers within the EU.'))
    vat_id_validated = models.BooleanField(default=False)
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

    def save(self, **kwargs):
        if self.order:
            self.order.touch()

        if self.name_parts:
            self.name_cached = self.name
        else:
            self.name_cached = ""
            self.name_parts = {}
        super().save(**kwargs)

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
        if not self.name_parts:
            return ""
        if '_legacy' in self.name_parts:
            return self.name_parts['_legacy']
        if '_scheme' in self.name_parts:
            scheme = PERSON_NAME_SCHEMES[self.name_parts['_scheme']]
        else:
            raise TypeError("Invalid name given.")
        return scheme['concatenation'](self.name_parts).strip()


def cachedticket_name(instance, filename: str) -> str:
    secret = get_random_string(length=16, allowed_chars=string.ascii_letters + string.digits)
    return 'tickets/{org}/{ev}/{code}-{no}-{prov}-{secret}.dat'.format(
        org=instance.order_position.order.event.organizer.slug,
        ev=instance.order_position.order.event.slug,
        prov=instance.provider,
        no=instance.order_position.positionid,
        code=instance.order_position.order.code,
        secret=secret,
        ext=os.path.splitext(filename)[1]
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
