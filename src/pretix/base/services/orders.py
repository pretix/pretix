from collections import Counter, namedtuple
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.i18n import (
    LazyDate, LazyLocaleException, LazyNumber, language,
)
from pretix.base.models import (
    CartPosition, Event, EventLock, Item, ItemVariation, Order, OrderPosition,
    Quota, User,
)
from pretix.base.models.orders import InvoiceAddress
from pretix.base.payment import BasePaymentProvider
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_qualified,
)
from pretix.base.services.mail import mail
from pretix.base.signals import (
    order_paid, order_placed, periodic_task, register_payment_providers,
)
from pretix.multidomain.urlreverse import build_absolute_uri

error_messages = {
    'unavailable': _('Some of the products you selected were no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected were no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'price_changed': _('The price of some of the items in your cart has changed in the '
                       'meantime. Please see below for details.'),
    'internal': _("An internal error occured, please try again."),
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'voucher_redeemed': _('A voucher you tried to use already has been used.'),
    'voucher_expired': _('A voucher you tried to use has expired.'),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period has ended.'),
    'voucher_invalid': _('This voucher code is not known in our database.'),
    'voucher_redeemed': _('This voucher code has already been used an can only be used once.'),
    'voucher_expired': _('This voucher is expired.'),
    'voucher_invalid_item': _('This voucher is not valid for this item.'),
    'voucher_required': _('You need a valid voucher code to order one of the products in your cart.'),
}


def mark_order_paid(order: Order, provider: str=None, info: str=None, date: datetime=None, manual: bool=None,
                    force: bool=False, send_mail: bool=True, user: User=None) -> Order:
    """
    Marks an order as paid. This sets the payment provider, info and date and returns
    the order object.

    :param provider: The payment provider that marked this as paid
    :type provider: str
    :param info: The information to store in order.payment_info
    :type info: str
    :param date: The date the payment was received (if you pass ``None``, the current
                 time will be used).
    :type date: datetime
    :param force: Whether this payment should be marked as paid even if no remaining
                  quota is available (default: ``False``).
    :type force: boolean
    :param send_mail: Whether an email should be sent to the user about this event (default: ``True``).
    :type send_mail: boolean
    :param user: The user that performed the change
    :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
    """
    with order.event.lock() as now_dt:
        can_be_paid = order._can_be_paid()
        if not force and can_be_paid is not True:
            raise Quota.QuotaExceededException(can_be_paid)
        order.payment_provider = provider or order.payment_provider
        order.payment_info = info or order.payment_info
        order.payment_date = date or now_dt
        if manual is not None:
            order.payment_manual = manual
        order.status = Order.STATUS_PAID
        order.save()

    order.log_action('pretix.event.order.paid', {
        'provider': provider,
        'info': info,
        'date': date,
        'manual': manual,
        'force': force
    }, user=user)
    order_paid.send(order.event, order=order)

    if send_mail:
        with language(order.locale):
            mail(
                order.email, _('Payment received for your order: %(code)s') % {'code': order.code},
                order.event.settings.mail_text_order_paid,
                {
                    'event': order.event.name,
                    'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                        'order': order.code,
                        'secret': order.secret
                    }),
                    'downloads': order.event.settings.get('ticket_download', as_type=bool)
                },
                order.event, locale=order.locale
            )
    return order


@transaction.atomic
def mark_order_refunded(order, user=None):
    """
    Mark this order as refunded. This sets the payment status and returns the order object.
    :param order: The order to change
    :param user: The user that performed the change
    """
    if isinstance(order, int):
        order = Order.objects.get(pk=order)
    if isinstance(user, int):
        user = User.objects.get(pk=user)
    with order.event.lock():
        order.status = Order.STATUS_REFUNDED
        order.save()

    order.log_action('pretix.event.order.refunded', user=user)
    i = order.invoices.filter(is_cancellation=False).last()
    if i:
        generate_cancellation(i)

    return order


@transaction.atomic
def cancel_order(order, user=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
    if isinstance(order, int):
        order = Order.objects.get(pk=order)
    if isinstance(user, int):
        user = User.objects.get(pk=user)
    with order.event.lock():
        if order.status != Order.STATUS_PENDING:
            raise OrderError(_('You cannot cancel this order.'))
        order.status = Order.STATUS_CANCELLED
        order.save()

    order.log_action('pretix.event.order.cancelled', user=user)
    i = order.invoices.filter(is_cancellation=False).last()
    if i:
        generate_cancellation(i)

    for position in order.positions.all():
        if position.voucher:
            position.voucher.redeemed = False
            position.voucher.save()

    return order


class OrderError(LazyLocaleException):
    pass


def _check_date(event: Event, now_dt: datetime):
    if event.presale_start and now_dt < event.presale_start:
        raise OrderError(error_messages['not_started'])
    if event.presale_end and now_dt > event.presale_end:
        raise OrderError(error_messages['ended'])


def _check_positions(event: Event, now_dt: datetime, positions: List[CartPosition]):
    err = None
    _check_date(event, now_dt)

    voucherids = set()
    for i, cp in enumerate(positions):
        if not cp.item.active:
            err = err or error_messages['unavailable']
            cp.delete()
            continue
        quotas = list(cp.item.quotas.all()) if cp.variation is None else list(cp.variation.quotas.all())

        if cp.voucher:
            if cp.voucher.redeemed or cp.voucher_id in voucherids:
                err = err or error_messages['voucher_redeemed']
                cp.delete()  # Sorry! But you should have never gotten into this state at all.
                continue
            voucherids.add(cp.voucher_id)

        if cp.item.require_voucher and cp.voucher is None:
            cp.delete()
            return error_messages['voucher_required']

        if cp.item.hide_without_voucher and (cp.voucher is None or cp.voucher.item is None
                                             or cp.voucher.item.pk != cp.item.pk):
            cp.delete()
            return error_messages['voucher_required']

        if cp.expires >= now_dt and not cp.voucher:
            # Other checks are not necessary
            continue

        price = cp.item.default_price if cp.variation is None else (
            cp.variation.default_price if cp.variation.default_price is not None else cp.item.default_price)

        if price is False or len(quotas) == 0:
            err = err or error_messages['unavailable']
            cp.delete()
            continue

        if cp.voucher:
            if cp.voucher.valid_until and cp.voucher.valid_until < now_dt:
                err = err or error_messages['voucher_expired']
                continue
            if cp.voucher.price is not None:
                price = cp.voucher.price

        if price != cp.price and not (cp.item.free_price and cp.price > price):
            positions[i] = cp
            cp.price = price
            cp.save()
            err = err or error_messages['price_changed']
            continue

        quota_ok = True

        ignore_all_quotas = cp.expires >= now_dt or (
            cp.voucher and (cp.voucher.allow_ignore_quota or (cp.voucher.block_quota and cp.voucher.quota is None)))

        if not ignore_all_quotas:
            for quota in quotas:
                if cp.voucher and cp.voucher.block_quota and cp.voucher.quota_id == quota.pk:
                    continue
                avail = quota.availability(now_dt)
                if avail[0] != Quota.AVAILABILITY_OK:
                    # This quota is sold out/currently unavailable, so do not sell this at all
                    err = err or error_messages['unavailable']
                    quota_ok = False
                    break

        if quota_ok:
            positions[i] = cp
            cp.expires = now_dt + timedelta(
                minutes=event.settings.get('reservation_time', as_type=int))
            cp.save()
        else:
            cp.delete()  # Sorry!
    if err:
        raise OrderError(err)


@transaction.atomic()
def _create_order(event: Event, email: str, positions: List[CartPosition], now_dt: datetime,
                  payment_provider: BasePaymentProvider, locale: str=None):
    total = sum([c.price for c in positions])
    payment_fee = payment_provider.calculate_fee(total)
    total += payment_fee
    expires = [now_dt + timedelta(days=event.settings.get('payment_term_days', as_type=int))]
    if event.settings.get('payment_term_last'):
        expires.append(event.settings.get('payment_term_last', as_type=datetime))
    order = Order.objects.create(
        status=Order.STATUS_PENDING,
        event=event,
        email=email,
        datetime=now_dt,
        expires=min(expires),
        locale=locale,
        total=total,
        payment_fee=payment_fee,
        payment_provider=payment_provider.identifier
    )
    OrderPosition.transform_cart_positions(positions, order)
    order.log_action('pretix.event.order.placed')
    order_placed.send(event, order=order)
    return order


def _perform_order(event: str, payment_provider: str, position_ids: List[str],
                   email: str, locale: str, address: int):

    event = Event.objects.get(id=event)
    responses = register_payment_providers.send(event)
    pprov = None
    for rec, response in responses:
        provider = response(event)
        if provider.identifier == payment_provider:
            pprov = provider
    if not pprov:
        raise OrderError(error_messages['internal'])

    with event.lock() as now_dt:
        positions = list(CartPosition.objects.filter(
            id__in=position_ids).select_related('item', 'variation'))
        if len(position_ids) != len(positions):
            raise OrderError(error_messages['internal'])
        _check_positions(event, now_dt, positions)
        order = _create_order(event, email, positions, now_dt, pprov,
                              locale=locale)

    if address is not None:
        try:
            addr = InvoiceAddress.objects.get(
                pk=address
            )
            if addr.order is not None:
                addr.pk = None
            addr.order = order
            addr.save()
        except InvoiceAddress.DoesNotExist:
            pass

    if event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        generate_invoice(order)

    with language(order.locale):
        if order.total == Decimal('0.00'):
            mailtext = event.settings.mail_text_order_free
        else:
            mailtext = event.settings.mail_text_order_placed
        mail(
            order.email, _('Your order: %(code)s') % {'code': order.code},
            mailtext,
            {
                'total': LazyNumber(order.total),
                'currency': event.currency,
                'date': LazyDate(order.expires),
                'event': event.name,
                'url': build_absolute_uri(event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }),
                'paymentinfo': str(pprov.order_pending_mail_render(order))
            },
            event, locale=order.locale
        )

    return order.id


def perform_order(event: str, payment_provider: str, positions: List[str],
                  email: str=None, locale: str=None, address: int=None):
    try:
        return _perform_order(event, payment_provider, positions, email, locale, address)
    except EventLock.LockTimeoutException:
        # Is raised when there are too many threads asking for event locks and we were
        # unable to get one
        raise OrderError(error_messages['busy'])


@receiver(signal=periodic_task)
def expire_orders(sender, **kwargs):
    eventcache = {}
    for o in Order.objects.filter(expires__lt=now(), status=Order.STATUS_PENDING).select_related('event'):
        expire = eventcache.get(o.event.pk, None)
        if expire is None:
            expire = o.event.settings.get('payment_term_expire_automatically', as_type=bool)
            eventcache[o.event.pk] = expire
        if expire:
            o.status = Order.STATUS_EXPIRED
            o.log_action('pretix.event.order.expired')
            o.save()


class OrderChangeManager:
    error_messages = {
        'free_to_paid': _('You cannot change a free order to a paid order.'),
        'product_without_variation': _('You need to select a variation of the product.'),
        'quota': _('The quota {name} does not have enough capacity left to perform the operation.'),
        'product_invalid': _('The selected product is not active or has no price set.'),
        'complete_cancel': _('This operation would leave the order empty. Please cancel the order itself instead.'),
        'not_pending': _('Only pending orders can be changed.'),
        'paid_to_free_exceeded': _('This operation would make the order free and therefore immediately paid, however '
                                   'no quota is available.'),
    }
    ItemOperation = namedtuple('ItemOperation', ('position', 'item', 'variation', 'price'))
    PriceOperation = namedtuple('PriceOperation', ('position', 'price'))
    CancelOperation = namedtuple('CancelOperation', ('position',))

    def __init__(self, order: Order, user):
        self.order = order
        self.user = user
        self._totaldiff = 0
        self._quotadiff = Counter()
        self._operations = []

    def change_item(self, position: OrderPosition, item: Item, variation: Optional[ItemVariation]):
        if (not variation and item.has_variations) or (variation and variation.item_id != item.pk):
            raise OrderError(self.error_messages['product_without_variation'])
        price = item.default_price if variation is None else (
            variation.default_price if variation.default_price is not None else item.default_price)
        if not price:
            raise OrderError(self.error_messages['product_invalid'])
        self._totaldiff = price - position.price
        self._quotadiff.update(variation.quotas.all() if variation else item.quotas.all())
        self._quotadiff.subtract(position.variation.quotas.all() if position.variation else position.item.quotas.all())
        self._operations.append(self.ItemOperation(position, item, variation, price))

    def change_price(self, position: OrderPosition, price: Decimal):
        self._totaldiff = price - position.price
        self._operations.append(self.PriceOperation(position, price))

    def cancel(self, position: OrderPosition):
        self._totaldiff = -position.price
        self._quotadiff.subtract(position.variation.quotas.all() if position.variation else position.item.quotas.all())
        self._operations.append(self.CancelOperation(position))

    def _check_quotas(self):
        for quota, diff in self._quotadiff.items():
            if diff <= 0:
                continue
            avail = quota.availability()
            if avail[0] != Quota.AVAILABILITY_OK or avail[1] < diff:
                raise OrderError(self.error_messages['quota'].format(name=quota.name))

    def _check_free_to_paid(self):
        if self.order.total == Decimal('0.00') and self._totaldiff > 0:
            raise OrderError(self.error_messages['free_to_paid'])

    def _check_paid_to_free(self):
        if self.order.total == 0:
            try:
                mark_order_paid(self.order, 'free', send_mail=False)
            except Quota.QuotaExceededException:
                raise OrderError(self.error_messages['paid_to_free_exceeded'])

    def _perform_operations(self):
        for op in self._operations:
            if isinstance(op, self.ItemOperation):
                self.order.log_action('pretix.event.order.changed.item', user=self.user, data={
                    'position': op.position.pk,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'new_item': op.item.pk,
                    'new_variation': op.variation.pk if op.variation else None,
                    'old_price': op.position.price,
                    'new_price': op.price
                })
                op.position.item = op.item
                op.position.variation = op.variation
                op.position.price = op.price
                op.position._calculate_tax()
                op.position.save()
            elif isinstance(op, self.PriceOperation):
                self.order.log_action('pretix.event.order.changed.price', user=self.user, data={
                    'position': op.position.pk,
                    'old_price': op.position.price,
                    'new_price': op.price
                })
                op.position.price = op.price
                op.position._calculate_tax()
                op.position.save()
            elif isinstance(op, self.CancelOperation):
                self.order.log_action('pretix.event.order.changed.cancel', user=self.user, data={
                    'position': op.position.pk,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'old_price': op.position.price,
                })
                op.position.delete()

    def _recalculate_total_and_payment_fee(self):
        self.order.total = sum([p.price for p in self.order.positions.all()])
        if self.order.total == 0:
            payment_fee = Decimal('0.00')
        else:
            payment_fee = self._get_payment_provider().calculate_fee(self.order.total)
        self.order.payment_fee = payment_fee
        self.order.total += payment_fee
        self.order._calculate_tax()
        self.order.save()

    def _reissue_invoice(self):
        i = self.order.invoices.filter(is_cancellation=False).last()
        if i:
            generate_cancellation(i)
            generate_invoice(self.order)

    def _check_complete_cancel(self):
        cancels = len([o for o in self._operations if isinstance(o, self.CancelOperation)])
        if cancels == self.order.positions.count():
            raise OrderError(self.error_messages['complete_cancel'])

    def _notify_user(self):
        with language(self.order.locale):
            mail(
                self.order.email, _('Your order has been changed: %(code)s') % {'code': self.order.code},
                self.order.event.settings.mail_text_order_changed,
                {
                    'event': self.order.event.name,
                    'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                        'order': self.order.code,
                        'secret': self.order.secret
                    }),
                },
                self.order.event, locale=self.order.locale
            )

    def commit(self):
        if not self._operations:
            # Do nothing
            return
        with transaction.atomic():
            with self.order.event.lock():
                if self.order.status != Order.STATUS_PENDING:
                    raise OrderError(self.error_messages['not_pending'])
                self._check_free_to_paid()
                self._check_quotas()
                self._check_complete_cancel()
                self._perform_operations()
            self._recalculate_total_and_payment_fee()
            self._reissue_invoice()
        self._check_paid_to_free()
        self._notify_user()

    def _get_payment_provider(self):
        responses = register_payment_providers.send(self.order.event)
        pprov = None
        for rec, response in responses:
            provider = response(self.order.event)
            if provider.identifier == self.order.payment_provider:
                return provider
        if not pprov:
            raise OrderError(error_messages['internal'])


if settings.HAS_CELERY:
    from pretix.celery import app

    @app.task(bind=True, max_retries=5, default_retry_delay=1)
    def perform_order_task(self, event: str, payment_provider: str, positions: List[str],
                           email: str=None, locale: str=None, address: int=None):
        try:
            try:
                return _perform_order(event, payment_provider, positions, email, locale, address)
            except EventLock.LockTimeoutException:
                self.retry(exc=OrderError(error_messages['busy']))
        except OrderError as e:
            return e

    @app.task(bind=True, max_retries=5, default_retry_delay=1)
    def cancel_order_task(self, order: int, user: int=None):
        try:
            try:
                return cancel_order(order, user)
            except EventLock.LockTimeoutException:
                self.retry(exc=OrderError(error_messages['busy']))
        except OrderError as e:
            return e

    perform_order.task = perform_order_task
    cancel_order.task = cancel_order_task
