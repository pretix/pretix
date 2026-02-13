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
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.utils.crypto import get_random_string
from django.utils.translation import gettext
from i18nfield.strings import LazyI18nString

from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderFee, OrderPosition, OrderRefund,
    SubEvent, TaxRule, User, WaitingListEntry,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import mail
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _cancel_order, _try_auto_refund,
)
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.services.tax import split_fee_for_taxes
from pretix.base.templatetags.money import money_filter
from pretix.celery_app import app
from pretix.helpers import OF_SELF
from pretix.helpers.format import format_map

logger = logging.getLogger(__name__)


def _send_wle_mail(wle: WaitingListEntry, subject: LazyI18nString, message: LazyI18nString, subevent: SubEvent):
    with language(wle.locale, wle.event.settings.region):
        email_context = get_email_context(event_or_subevent=subevent or wle.event, event=wle.event)
        mail(
            wle.email,
            format_map(subject, email_context),
            message,
            email_context,
            wle.event,
            locale=wle.locale
        )


def _send_mail(order: Order, subject: LazyI18nString, message: LazyI18nString, subevent: SubEvent,
               refund_amount: Decimal, user: User, positions: list):
    with language(order.locale, order.event.settings.region):
        try:
            ia = order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = InvoiceAddress(order=order)

        email_context = get_email_context(event_or_subevent=subevent or order.event, refund_amount=refund_amount,
                                          order=order, position_or_address=ia, event=order.event)
        real_subject = format_map(subject, email_context)
        order.send_mail(
            real_subject, message, email_context,
            'pretix.event.order.email.event_canceled',
            user,
        )

        for p in positions:
            if subevent and p.subevent_id != subevent.id:
                continue

            if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                real_subject = format_map(subject, email_context)
                email_context = get_email_context(event_or_subevent=p.subevent or order.event,
                                                  event=order.event,
                                                  refund_amount=refund_amount,
                                                  position_or_address=p,
                                                  order=order, position=p)
                order.send_mail(
                    real_subject, message, email_context,
                    'pretix.event.order.email.event_canceled',
                    position=p,
                    user=user
                )


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def cancel_event(self, event: Event, subevent: int, auto_refund: bool,
                 keep_fee_fixed: str, keep_fee_per_ticket: str, keep_fee_percentage: str, keep_fees: list=None,
                 manual_refund: bool=False, send: bool=False, send_subject: dict=None, send_message: dict=None,
                 send_waitinglist: bool=False, send_waitinglist_subject: dict={}, send_waitinglist_message: dict={},
                 user: int=None, refund_as_giftcard: bool=False, giftcard_expires=None, giftcard_conditions=None,
                 subevents_from: str=None, subevents_to: str=None, dry_run=False):
    send_subject = LazyI18nString(send_subject)
    send_message = LazyI18nString(send_message)
    send_waitinglist_subject = LazyI18nString(send_waitinglist_subject)
    send_waitinglist_message = LazyI18nString(send_waitinglist_message)
    if user:
        user = User.objects.get(pk=user)

    s = OrderPosition.objects.filter(
        order=OuterRef('pk')
    ).order_by().values('order').annotate(k=Count('id')).values('k')
    has_blocked = OrderPosition.objects.filter(order_id=OuterRef('pk'), blocked__isnull=False)
    orders_to_cancel = event.orders.annotate(
        pcnt=Subquery(s, output_field=IntegerField()),
        has_blocked=Exists(has_blocked),
    ).filter(
        status__in=[Order.STATUS_PAID, Order.STATUS_PENDING, Order.STATUS_EXPIRED],
        pcnt__gt=0,
    ).all()

    if subevent or subevents_from:
        if subevent:
            subevents = event.subevents.filter(pk=subevent)
            subevent = subevents.first()
            subevent_ids = {subevent.pk}
        else:
            subevents = event.subevents.filter(date_from__gte=subevents_from, date_from__lt=subevents_to)
            subevent_ids = set(subevents.values_list('id', flat=True))

        has_subevent = OrderPosition.objects.filter(order_id=OuterRef('pk')).filter(
            subevent__in=subevents
        )
        has_other_subevent = OrderPosition.objects.filter(order_id=OuterRef('pk')).exclude(
            subevent__in=subevents
        )
        orders_to_change = orders_to_cancel.annotate(
            has_subevent=Exists(has_subevent),
            has_other_subevent=Exists(has_other_subevent),
        ).filter(
            Q(has_subevent=True, has_other_subevent=True) |
            Q(has_subevent=True, has_blocked=True)
        )
        orders_to_cancel = orders_to_cancel.annotate(
            has_subevent=Exists(has_subevent),
            has_other_subevent=Exists(has_other_subevent),
        ).filter(
            has_subevent=True, has_other_subevent=False, has_blocked=False
        )

        if not dry_run:
            for se in subevents:
                se.log_action(
                    'pretix.subevent.canceled', user=user,
                    data={
                        "auto_refund": auto_refund,
                        "keep_fee_fixed": keep_fee_fixed,
                        "keep_fee_per_ticket": keep_fee_per_ticket,
                        "keep_fee_percentage": keep_fee_percentage,
                        "keep_fees": keep_fees,
                        "manual_refund": manual_refund,
                        "send": send,
                        "send_subject": send_subject,
                        "send_message": send_message,
                        "send_waitinglist": send_waitinglist,
                        "send_waitinglist_subject": send_waitinglist_subject,
                        "send_waitinglist_message": send_waitinglist_message,
                        "refund_as_giftcard": refund_as_giftcard,
                        "giftcard_expires": str(giftcard_expires),
                        "giftcard_conditions": giftcard_conditions,
                    }
                )
                se.active = False
                se.save(update_fields=['active'])
                se.log_action(
                    'pretix.subevent.changed', user=user, data={'active': False, '_source': 'cancel_event'}
                )
    else:
        subevents = None
        subevent_ids = set()
        orders_to_change = orders_to_cancel.filter(has_blocked=True)
        orders_to_cancel = orders_to_cancel.filter(has_blocked=False)

        if not dry_run:
            event.log_action(
                'pretix.event.canceled', user=user,
                data={
                    "auto_refund": auto_refund,
                    "keep_fee_fixed": keep_fee_fixed,
                    "keep_fee_per_ticket": keep_fee_per_ticket,
                    "keep_fee_percentage": keep_fee_percentage,
                    "keep_fees": keep_fees,
                    "manual_refund": manual_refund,
                    "send": send,
                    "send_subject": send_subject,
                    "send_message": send_message,
                    "send_waitinglist": send_waitinglist,
                    "send_waitinglist_subject": send_waitinglist_subject,
                    "send_waitinglist_message": send_waitinglist_message,
                    "refund_as_giftcard": refund_as_giftcard,
                    "giftcard_expires": str(giftcard_expires),
                    "giftcard_conditions": giftcard_conditions,
                }
            )

            for i in event.items.filter(active=True):
                i.active = False
                i.save(update_fields=['active'])
                i.log_action(
                    'pretix.event.item.changed', user=user, data={'active': False, '_source': 'cancel_event'}
                )
    failed = 0
    refund_total = Decimal("0.00")
    cancel_full_total = orders_to_cancel.count()
    cancel_partial_total = orders_to_change.count()
    total = cancel_full_total + cancel_partial_total
    qs_wl = event.waitinglistentries.filter(voucher__isnull=True).select_related('subevent')
    if subevents:
        qs_wl = qs_wl.filter(subevent__in=subevents)
    if send_waitinglist:
        total += qs_wl.count()
    counter = 0
    self.update_state(
        state='PROGRESS',
        meta={'value': 0}
    )

    for o in orders_to_cancel.only('id', 'total').iterator():
        payment_refund_sum = o.payment_refund_sum  # cache to avoid multiple computations
        try:
            fee = Decimal('0.00')
            fee_sum = Decimal('0.00')
            keep_fee_objects = []
            if keep_fees:
                for f in o.fees.all():
                    if f.fee_type in keep_fees:
                        fee += f.value
                        keep_fee_objects.append(f)
                    fee_sum += f.value
            if keep_fee_percentage:
                fee += Decimal(keep_fee_percentage) / Decimal('100.00') * (o.total - fee_sum)
            if keep_fee_fixed:
                fee += Decimal(keep_fee_fixed)
            if keep_fee_per_ticket:
                for p in o.positions.all():
                    if p.addon_to_id is None:
                        fee += min(p.price, Decimal(keep_fee_per_ticket))
            fee = round_decimal(min(fee, payment_refund_sum), event.currency)

            if dry_run:
                refund_total += max(Decimal("0.00"), min(payment_refund_sum, o.total - fee))
            else:
                _cancel_order(o.pk, user, send_mail=False, cancellation_fee=fee, keep_fees=keep_fee_objects)
                refund_amount = payment_refund_sum
                refund_amount += refund_total

                try:
                    if auto_refund or manual_refund:
                        _try_auto_refund(o.pk, auto_refund=auto_refund, manual_refund=manual_refund, allow_partial=True,
                                         source=OrderRefund.REFUND_SOURCE_ADMIN, refund_as_giftcard=refund_as_giftcard,
                                         giftcard_expires=giftcard_expires, giftcard_conditions=giftcard_conditions,
                                         comment=gettext('Event canceled'))
                finally:
                    if send:
                        _send_mail(o, send_subject, send_message, subevent, refund_amount, user, o.positions.all())

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100 if total else 0, 2)}
                )
        except LockTimeoutException:
            logger.exception("Could not cancel order")
            failed += 1
        except OrderError:
            logger.exception("Could not cancel order")
            failed += 1

    for o in orders_to_change.values_list('id', flat=True).iterator():
        with transaction.atomic():
            if dry_run:
                o = event.orders.get(pk=o)
            else:
                o = event.orders.select_for_update(of=OF_SELF).get(pk=o)
            total = Decimal('0.00')
            fee = Decimal('0.00')
            positions = []

            ocm = OrderChangeManager(o, user=user, notify=False)
            payment_refund_sum = o.payment_refund_sum  # cache to avoid multiple computations
            for p in o.positions.all():
                if (not event.has_subevents or p.subevent_id in subevent_ids) and not p.blocked:
                    total += p.price
                    ocm.cancel(p)
                    positions.append(p)

                    if keep_fee_per_ticket:
                        if p.addon_to_id is None:
                            fee += min(p.price, Decimal(keep_fee_per_ticket))

            if keep_fee_fixed:
                fee += Decimal(keep_fee_fixed)
            if keep_fee_percentage:
                fee += Decimal(keep_fee_percentage) / Decimal('100.00') * total
            fee = round_decimal(min(fee, payment_refund_sum), event.currency)
            if fee:
                tax_rule_zero = TaxRule.zero()
                if event.settings.tax_rule_cancellation == "default":
                    fee_values = [(event.cached_default_tax_rule or tax_rule_zero, fee)]
                elif event.settings.tax_rule_cancellation == "split":
                    fee_values = split_fee_for_taxes(positions, fee, event)
                else:
                    fee_values = [(tax_rule_zero, fee)]

                try:
                    ia = o.invoice_address
                except InvoiceAddress.DoesNotExist:
                    ia = None

                for tax_rule, price in fee_values:
                    tax_rule = tax_rule or tax_rule_zero
                    tax = tax_rule.tax(
                        price, invoice_address=ia, base_price_is="gross"
                    )
                    f = OrderFee(
                        fee_type=OrderFee.FEE_TYPE_CANCELLATION,
                        value=price,
                        order=o,
                        tax_rate=tax.rate,
                        tax_code=tax.code,
                        tax_value=tax.tax,
                        tax_rule=tax_rule,
                    )
                    ocm.add_fee(f)

            if dry_run:
                refund_total += max(payment_refund_sum - (o.total + ocm._totaldiff_guesstimate), Decimal("0.00"))
            else:
                ocm.commit()
                refund_amount = payment_refund_sum - o.total
                refund_total += refund_amount

                if auto_refund or manual_refund:
                    _try_auto_refund(o.pk, auto_refund=auto_refund, manual_refund=manual_refund, allow_partial=True,
                                     source=OrderRefund.REFUND_SOURCE_ADMIN, refund_as_giftcard=refund_as_giftcard,
                                     giftcard_expires=giftcard_expires, giftcard_conditions=giftcard_conditions,
                                     comment=gettext('Event canceled'))

                if send:
                    _send_mail(o, send_subject, send_message, subevent, refund_amount, user, positions)

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100 if total else 0, 2)}
                )

    if send_waitinglist:
        for wle in qs_wl:
            if not dry_run:
                _send_wle_mail(wle, send_waitinglist_subject, send_waitinglist_message, wle.subevent)

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100 if total else 0, 2)}
                )

    confirmation_code = None
    if dry_run and user and refund_total > Decimal('100.00'):
        confirmation_code = get_random_string(8, allowed_chars="01234567890")
        mail(
            user.email,
            subject=gettext('Bulk-refund confirmation'),
            template='pretixbase/email/cancel_confirm.txt',
            context={
                "event": str(event),
                "amount": money_filter(refund_total, event.currency),
                "confirmation_code": confirmation_code,
            },
            locale=user.locale,
        )

    return {
        "dry_run": dry_run,
        "id": self.request.id,
        "failed": failed,
        "refund_total": refund_total,
        "cancel_full_total": cancel_full_total,
        "cancel_partial_total": cancel_partial_total,
        "confirmation_code": confirmation_code,
        "args": self.request.args,
        "kwargs": self.request.kwargs,
    }
