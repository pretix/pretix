import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import (
    Count, Exists, IntegerField, OuterRef, Subquery, Sum,
)
from i18nfield.strings import LazyI18nString

from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    Event, InvoiceAddress, Order, OrderFee, OrderPosition, SubEvent, User,
    WaitingListEntry,
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
            ia = InvoiceAddress()

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
                 keep_fee_percentage: str, keep_fees: bool,
                 send: bool, send_subject: dict, send_message: dict,
                 send_waitinglist: bool=False, send_waitinglist_subject: dict={}, send_waitinglist_message: dict={},
                 user: int=None):
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

    for o in orders_to_cancel.only('id', 'total'):
        try:
            refund_amount = Decimal('0.00')

            fee = Decimal('0.00')
            if keep_fees:
                fee += o.fees.filter(
                    fee_type__in=(OrderFee.FEE_TYPE_PAYMENT, OrderFee.FEE_TYPE_SHIPPING, OrderFee.FEE_TYPE_SERVICE,
                                  OrderFee.FEE_TYPE_CANCELLATION)
                ).aggregate(
                    s=Sum('value')
                )['s'] or 0
            if keep_fee_percentage:
                fee += Decimal(keep_fee_percentage) / Decimal('100.00') * (o.total - fee)
            if keep_fee_fixed:
                fee += Decimal(keep_fee_fixed)
            fee = round_decimal(min(fee, o.payment_refund_sum), event.currency)

            _cancel_order(o.pk, user, send_mail=False, cancellation_fee=fee)
            if auto_refund:
                _try_auto_refund(o.pk)

            if send:
                _send_mail(o, send_subject, send_message, subevent, refund_amount, user, o.positions.all())
        except LockTimeoutException:
            logger.exception("Could not cancel order")
            failed += 1
        except OrderError:
            logger.exception("Could not cancel order")
            failed += 1

    for o in orders_to_change.values_list('id', flat=True):
        with transaction.atomic():
            o = event.orders.select_for_update().get(pk=o)
            refund_amount = Decimal('0.00')
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
            if auto_refund:
                _try_auto_refund(o.pk)

            if send:
                _send_mail(o, send_subject, send_message, subevent, refund_amount, user, positions)

    for wle in event.waitinglistentries.filter(subevent=subevent, voucher__isnull=True):
        _send_wle_mail(wle, send_waitinglist_subject, send_waitinglist_message, subevent)

    return failed
