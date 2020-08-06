import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery
from i18nfield.strings import LazyI18nString

from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderFee, OrderPosition, OrderRefund,
    SubEvent, User, WaitingListEntry,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, TolerantDict, mail
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, _cancel_order, _try_auto_refund,
)
from pretix.base.services.tasks import ProfiledEventTask
from pretix.celery_app import app

logger = logging.getLogger(__name__)


def _send_wle_mail(wle: WaitingListEntry, subject: LazyI18nString, message: LazyI18nString, subevent: SubEvent):
    with language(wle.locale):
        email_context = get_email_context(event_or_subevent=subevent or wle.event, event=wle.event)
        try:
            mail(
                wle.email,
                str(subject).format_map(TolerantDict(email_context)),
                message,
                email_context,
                wle.event,
                locale=wle.locale
            )
        except SendMailException:
            logger.exception('Waiting list canceled email could not be sent')


def _send_mail(order: Order, subject: LazyI18nString, message: LazyI18nString, subevent: SubEvent,
               refund_amount: Decimal, user: User, positions: list):
    with language(order.locale):
        try:
            ia = order.invoice_address
        except InvoiceAddress.DoesNotExist:
            ia = InvoiceAddress(order=order)

        email_context = get_email_context(event_or_subevent=subevent or order.event, refund_amount=refund_amount,
                                          order=order, position_or_address=ia, event=order.event)
        real_subject = str(subject).format_map(TolerantDict(email_context))
        try:
            order.send_mail(
                real_subject, message, email_context,
                'pretix.event.order.email.event_canceled',
                user,
            )
        except SendMailException:
            logger.exception('Order canceled email could not be sent')

        for p in positions:
            if subevent and p.subevent_id != subevent.id:
                continue

            if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                real_subject = str(subject).format_map(TolerantDict(email_context))
                email_context = get_email_context(event_or_subevent=subevent or order.event,
                                                  event=order.event,
                                                  refund_amount=refund_amount,
                                                  position_or_address=p,
                                                  order=order, position=p)
                try:
                    order.send_mail(
                        real_subject, message, email_context,
                        'pretix.event.order.email.event_canceled',
                        position=p,
                        user=user
                    )
                except SendMailException:
                    logger.exception('Order canceled email could not be sent to attendee')


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def cancel_event(self, event: Event, subevent: int, auto_refund: bool, keep_fee_fixed: str,
                 keep_fee_percentage: str, keep_fees: list=None, manual_refund: bool=False,
                 send: bool=False, send_subject: dict=None, send_message: dict=None,
                 send_waitinglist: bool=False, send_waitinglist_subject: dict={}, send_waitinglist_message: dict={},
                 user: int=None, refund_as_giftcard: bool=False, giftcard_expires=None, giftcard_conditions=None):
    send_subject = LazyI18nString(send_subject)
    send_message = LazyI18nString(send_message)
    send_waitinglist_subject = LazyI18nString(send_waitinglist_subject)
    send_waitinglist_message = LazyI18nString(send_waitinglist_message)
    if user:
        user = User.objects.get(pk=user)

    s = OrderPosition.objects.filter(
        order=OuterRef('pk')
    ).order_by().values('order').annotate(k=Count('id')).values('k')
    orders_to_cancel = event.orders.annotate(pcnt=Subquery(s, output_field=IntegerField())).filter(
        status__in=[Order.STATUS_PAID, Order.STATUS_PENDING, Order.STATUS_EXPIRED],
        pcnt__gt=0
    ).all()

    if subevent:
        subevent = event.subevents.get(pk=subevent)

        has_subevent = OrderPosition.objects.filter(order_id=OuterRef('pk')).filter(
            subevent=subevent
        )
        has_other_subevent = OrderPosition.objects.filter(order_id=OuterRef('pk')).exclude(
            subevent=subevent
        )
        orders_to_change = orders_to_cancel.annotate(
            has_subevent=Exists(has_subevent),
            has_other_subevent=Exists(has_other_subevent),
        ).filter(
            has_subevent=True, has_other_subevent=True
        )
        orders_to_cancel = orders_to_cancel.annotate(
            has_subevent=Exists(has_subevent),
            has_other_subevent=Exists(has_other_subevent),
        ).filter(
            has_subevent=True, has_other_subevent=False
        )

        subevent.log_action(
            'pretix.subevent.canceled', user=user,
        )
        subevent.active = False
        subevent.save(update_fields=['active'])
        subevent.log_action(
            'pretix.subevent.changed', user=user, data={'active': False, '_source': 'cancel_event'}
        )
    else:
        orders_to_change = event.orders.none()
        event.log_action(
            'pretix.event.canceled', user=user,
        )

        for i in event.items.filter(active=True):
            i.active = False
            i.save(update_fields=['active'])
            i.log_action(
                'pretix.event.item.changed', user=user, data={'active': False, '_source': 'cancel_event'}
            )
    failed = 0
    total = orders_to_cancel.count() + orders_to_change.count()
    qs_wl = event.waitinglistentries.filter(subevent=subevent, voucher__isnull=True)
    if send_waitinglist:
        total += qs_wl.count()
    counter = 0
    self.update_state(
        state='PROGRESS',
        meta={'value': 0}
    )

    for o in orders_to_cancel.only('id', 'total').iterator():
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
            fee = round_decimal(min(fee, o.payment_refund_sum), event.currency)

            _cancel_order(o.pk, user, send_mail=False, cancellation_fee=fee, keep_fees=keep_fee_objects)
            refund_amount = o.payment_refund_sum

            try:
                if auto_refund:
                    _try_auto_refund(o.pk, manual_refund=manual_refund, allow_partial=True,
                                     source=OrderRefund.REFUND_SOURCE_ADMIN, refund_as_giftcard=refund_as_giftcard,
                                     giftcard_expires=giftcard_expires, giftcard_conditions=giftcard_conditions)
            finally:
                if send:
                    _send_mail(o, send_subject, send_message, subevent, refund_amount, user, o.positions.all())

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100, 2)}
                )
        except LockTimeoutException:
            logger.exception("Could not cancel order")
            failed += 1
        except OrderError:
            logger.exception("Could not cancel order")
            failed += 1

    for o in orders_to_change.values_list('id', flat=True).iterator():
        with transaction.atomic():
            o = event.orders.select_for_update().get(pk=o)
            total = Decimal('0.00')
            positions = []

            ocm = OrderChangeManager(o, user=user, notify=False)
            for p in o.positions.all():
                if p.subevent == subevent:
                    total += p.price
                    ocm.cancel(p)
                    positions.append(p)

            fee = Decimal('0.00')
            if keep_fee_fixed:
                fee += Decimal(keep_fee_fixed)
            if keep_fee_percentage:
                fee += Decimal(keep_fee_percentage) / Decimal('100.00') * total
            fee = round_decimal(min(fee, o.payment_refund_sum), event.currency)
            if fee:
                f = OrderFee(
                    fee_type=OrderFee.FEE_TYPE_CANCELLATION,
                    value=fee,
                    order=o,
                    tax_rule=o.event.settings.tax_rate_default,
                )
                f._calculate_tax()
                ocm.add_fee(f)

            ocm.commit()
            refund_amount = o.payment_refund_sum - o.total

            if auto_refund:
                _try_auto_refund(o.pk, manual_refund=manual_refund, allow_partial=True,
                                 source=OrderRefund.REFUND_SOURCE_ADMIN, refund_as_giftcard=refund_as_giftcard,
                                 giftcard_expires=giftcard_expires, giftcard_conditions=giftcard_conditions)

            if send:
                _send_mail(o, send_subject, send_message, subevent, refund_amount, user, positions)

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100, 2)}
                )

    if send_waitinglist:
        for wle in qs_wl:
            _send_wle_mail(wle, send_waitinglist_subject, send_waitinglist_message, subevent)

            counter += 1
            if not self.request.called_directly and counter % max(10, total // 100) == 0:
                self.update_state(
                    state='PROGRESS',
                    meta={'value': round(counter / total * 100, 2)}
                )
    return failed
