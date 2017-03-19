import json
import logging
from collections import Counter, namedtuple
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import pytz
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.timezone import make_aware, now
from django.utils.translation import ugettext as _

from pretix.base.i18n import (
    LazyDate, LazyLocaleException, LazyNumber, language,
)
from pretix.base.models import (
    CartPosition, Event, Item, ItemVariation, Order, OrderPosition, Quota,
    User, Voucher,
)
from pretix.base.models.orders import CachedTicket, InvoiceAddress
from pretix.base.payment import BasePaymentProvider
from pretix.base.services.async import ProfiledTask
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_qualified,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, mail
from pretix.base.signals import (
    order_paid, order_placed, periodic_task, register_payment_providers,
)
from pretix.celery_app import app
from pretix.multidomain.urlreverse import build_absolute_uri

error_messages = {
    'unavailable': _('Some of the products you selected were no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected were no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'price_changed': _('The price of some of the items in your cart has changed in the '
                       'meantime. Please see below for details.'),
    'internal': _("An internal error occured, please try again."),
    'empty': _("Your cart is empty."),
    'max_items_per_product': _("You cannot select more than %(max)s items of the product %(product)s. We removed the "
                               "surplus items from your cart."),
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period has ended.'),
    'voucher_invalid': _('The voucher code used for one of the items in your cart is not known in our database.'),
    'voucher_redeemed': _('The voucher code used for one of the items in your cart has already been used the maximum '
                          'number of times allowed. We removed this item from your cart.'),
    'voucher_expired': _('The voucher code used for one of the items in your cart is expired. We removed this item '
                         'from your cart.'),
    'voucher_invalid_item': _('The voucher code used for one of the items in your cart is not valid for this item. We '
                              'removed this item from your cart.'),
    'voucher_required': _('You need a valid voucher code to order one of the products in your cart. We removed this '
                          'item from your cart.'),
}

logger = logging.getLogger(__name__)


def mark_order_paid(order: Order, provider: str=None, info: str=None, date: datetime=None, manual: bool=None,
                    force: bool=False, send_mail: bool=True, user: User=None, mail_text='') -> Order:
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
    :param mail_text: Additional text to be included in the email
    :type mail_text: str
    :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
    """
    if order.status == Order.STATUS_PAID:
        return order

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
        'date': date or now_dt,
        'manual': manual,
        'force': force
    }, user=user)
    order_paid.send(order.event, order=order)

    if order.event.settings.get('invoice_generate') in ('True', 'paid') and invoice_qualified(order):
        if not order.invoices.exists():
            generate_invoice(order)

    if send_mail:
        with language(order.locale):
            try:
                invoice_name = order.invoice_address.name
                invoice_company = order.invoice_address.company
            except InvoiceAddress.DoesNotExist:
                invoice_name = ""
                invoice_company = ""
            mail(
                order.email, _('Payment received for your order: %(code)s') % {'code': order.code},
                order.event.settings.mail_text_order_paid,
                {
                    'event': order.event.name,
                    'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                        'order': order.code,
                        'secret': order.secret
                    }),
                    'downloads': order.event.settings.get('ticket_download', as_type=bool),
                    'invoice_name': invoice_name,
                    'invoice_company': invoice_company,
                    'payment_info': mail_text
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
def _cancel_order(order, user=None):
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
        order.status = Order.STATUS_CANCELED
        order.save()

    order.log_action('pretix.event.order.canceled', user=user)
    i = order.invoices.filter(is_cancellation=False).last()
    if i:
        generate_cancellation(i)

    for position in order.positions.all():
        if position.voucher:
            Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=F('redeemed') - 1)

    return order.pk


class OrderError(LazyLocaleException):
    pass


def _check_date(event: Event, now_dt: datetime):
    if event.presale_start and now_dt < event.presale_start:
        raise OrderError(error_messages['not_started'])
    if event.presale_end and now_dt > event.presale_end:
        raise OrderError(error_messages['ended'])


def _check_positions(event: Event, now_dt: datetime, positions: List[CartPosition]):
    err = None
    errargs = None
    _check_date(event, now_dt)

    products_seen = Counter()
    for i, cp in enumerate(positions):
        if not cp.item.active or (cp.variation and not cp.variation.active):
            err = err or error_messages['unavailable']
            cp.delete()
            continue
        quotas = list(cp.item.quotas.all()) if cp.variation is None else list(cp.variation.quotas.all())

        products_seen[cp.item] += 1
        if cp.item.max_per_order and products_seen[cp.item] > cp.item.max_per_order:
            err = error_messages['max_items_per_product']
            errargs = {'max': cp.item.max_per_order,
                       'product': cp.item.name}
            cp.delete()  # Sorry!
            break

        if cp.voucher:
            redeemed_in_carts = CartPosition.objects.filter(
                Q(voucher=cp.voucher) & Q(event=event) & Q(expires__gte=now_dt)
            ).exclude(pk=cp.pk)
            v_avail = cp.voucher.max_usages - cp.voucher.redeemed - redeemed_in_carts.count()
            if v_avail < 1:
                err = err or error_messages['voucher_redeemed']
                cp.delete()  # Sorry!
                continue

        if cp.item.require_voucher and cp.voucher is None:
            cp.delete()
            err = error_messages['voucher_required']
            break

        if cp.item.hide_without_voucher and (cp.voucher is None or cp.voucher.item is None
                                             or cp.voucher.item.pk != cp.item.pk):
            cp.delete()
            err = error_messages['voucher_required']
            break

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
                cp.delete()
                continue
            price = cp.voucher.calculate_price(price)

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
        raise OrderError(err, errargs)


def _create_order(event: Event, email: str, positions: List[CartPosition], now_dt: datetime,
                  payment_provider: BasePaymentProvider, locale: str=None, address: int=None,
                  meta_info: dict=None):
    from datetime import date, time

    total = sum([c.price for c in positions])
    payment_fee = payment_provider.calculate_fee(total)
    total += payment_fee

    tz = pytz.timezone(event.settings.timezone)
    exp_by_date = now_dt.astimezone(tz) + timedelta(days=event.settings.get('payment_term_days', as_type=int))
    exp_by_date = exp_by_date.astimezone(tz).replace(hour=23, minute=59, second=59, microsecond=0)
    if event.settings.get('payment_term_weekdays'):
        if exp_by_date.weekday() == 5:
            exp_by_date += timedelta(days=2)
        elif exp_by_date.weekday() == 6:
            exp_by_date += timedelta(days=1)

    expires = exp_by_date

    if event.settings.get('payment_term_last'):
        last_date = make_aware(datetime.combine(
            event.settings.get('payment_term_last', as_type=date),
            time(hour=23, minute=59, second=59)
        ), tz)
        if last_date < expires:
            expires = last_date

    with transaction.atomic():
        order = Order.objects.create(
            status=Order.STATUS_PENDING,
            event=event,
            email=email,
            datetime=now_dt,
            expires=expires,
            locale=locale,
            total=total,
            payment_fee=payment_fee,
            payment_provider=payment_provider.identifier,
            meta_info=json.dumps(meta_info or {}),
        )
        OrderPosition.transform_cart_positions(positions, order)

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

        order.log_action('pretix.event.order.placed')

    order_placed.send(event, order=order)
    return order


def _perform_order(event: str, payment_provider: str, position_ids: List[str],
                   email: str, locale: str, address: int, meta_info: dict=None):

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
        if len(positions) == 0:
            raise OrderError(error_messages['empty'])
        if len(position_ids) != len(positions):
            raise OrderError(error_messages['internal'])
        _check_positions(event, now_dt, positions)
        order = _create_order(event, email, positions, now_dt, pprov,
                              locale=locale, address=address, meta_info=meta_info)

    if event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        if not order.invoices.exists():
            generate_invoice(order)

    if order.total == Decimal('0.00'):
        mailtext = event.settings.mail_text_order_free
    else:
        mailtext = event.settings.mail_text_order_placed

    try:
        invoice_name = order.invoice_address.name
        invoice_company = order.invoice_address.company
    except InvoiceAddress.DoesNotExist:
        invoice_name = ""
        invoice_company = ""

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
            'paymentinfo': str(pprov.order_pending_mail_render(order)),
            'invoice_name': invoice_name,
            'invoice_company': invoice_company,
        },
        event, locale=order.locale
    )

    return order.id


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


@receiver(signal=periodic_task)
def send_expiry_warnings(sender, **kwargs):
    eventcache = {}
    today = now().replace(hour=0, minute=0, second=0)

    for o in Order.objects.filter(expires__gte=today, expiry_reminder_sent=False, status=Order.STATUS_PENDING).select_related('event'):
        eventsettings = eventcache.get(o.event.pk, None)
        if eventsettings is None:
            eventsettings = o.event.settings
            eventcache[o.event.pk] = eventsettings

        days = eventsettings.get('mail_days_order_expire_warning', as_type=int)
        tz = pytz.timezone(eventsettings.get('timezone', settings.TIME_ZONE))
        if days and (o.expires - today).days <= days:
            o.expiry_reminder_sent = True
            o.save()
            try:
                invoice_name = o.invoice_address.name
                invoice_company = o.invoice_address.company
            except InvoiceAddress.DoesNotExist:
                invoice_name = ""
                invoice_company = ""
            try:
                with language(o.locale):
                    mail(
                        o.email, _('Your order is about to expire: %(code)s') % {'code': o.code},
                        eventsettings.mail_text_order_expire_warning,
                        {
                            'event': o.event.name,
                            'url': build_absolute_uri(o.event, 'presale:event.order', kwargs={
                                'order': o.code,
                                'secret': o.secret
                            }),
                            'expire_date': date_format(o.expires.astimezone(tz), 'SHORT_DATE_FORMAT'),
                            'invoice_name': invoice_name,
                            'invoice_company': invoice_company,
                        },
                        o.event, locale=o.locale
                    )
            except SendMailException:
                logger.exception('Reminder email could not be sent')
            else:
                o.log_action('pretix.event.order.expire_warning_sent')


class OrderChangeManager:
    error_messages = {
        'free_to_paid': _('You cannot change a free order to a paid order.'),
        'product_without_variation': _('You need to select a variation of the product.'),
        'quota': _('The quota {name} does not have enough capacity left to perform the operation.'),
        'product_invalid': _('The selected product is not active or has no price set.'),
        'complete_cancel': _('This operation would leave the order empty. Please cancel the order itself instead.'),
        'not_pending_or_paid': _('Only pending or paid orders can be changed.'),
        'paid_to_free_exceeded': _('This operation would make the order free and therefore immediately paid, however '
                                   'no quota is available.'),
        'paid_price_change': _('Currently, paid orders can only be changed in a way that does not change the total '
                               'price of the order as partial payments or refunds are not yet supported.')
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
        price = item.default_price if variation is None else variation.price
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
            if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < diff):
                raise OrderError(self.error_messages['quota'].format(name=quota.name))

    def _check_free_to_paid(self):
        if self.order.total == Decimal('0.00') and self._totaldiff > 0:
            raise OrderError(self.error_messages['free_to_paid'])

    def _check_paid_price_change(self):
        if self.order.status == Order.STATUS_PAID and self._totaldiff != 0:
            raise OrderError(self.error_messages['paid_price_change'])

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
                    'positionid': op.position.positionid,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'new_item': op.item.pk,
                    'new_variation': op.variation.pk if op.variation else None,
                    'old_price': op.position.price,
                    'addon_to': op.position.addon_to_id,
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
                    'positionid': op.position.positionid,
                    'old_price': op.position.price,
                    'addon_to': op.position.addon_to_id,
                    'new_price': op.price
                })
                op.position.price = op.price
                op.position._calculate_tax()
                op.position.save()
            elif isinstance(op, self.CancelOperation):
                for opa in op.position.addons.all():
                    self.order.log_action('pretix.event.order.changed.cancel', user=self.user, data={
                        'position': opa.pk,
                        'positionid': opa.positionid,
                        'old_item': opa.item.pk,
                        'old_variation': opa.variation.pk if opa.variation else None,
                        'addon_to': opa.addon_to_id,
                        'old_price': opa.price,
                    })
                self.order.log_action('pretix.event.order.changed.cancel', user=self.user, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'old_price': op.position.price,
                    'addon_to': None,
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
            try:
                invoice_name = self.order.invoice_address.name
                invoice_company = self.order.invoice_address.company
            except InvoiceAddress.DoesNotExist:
                invoice_name = ""
                invoice_company = ""
            mail(
                self.order.email, _('Your order has been changed: %(code)s') % {'code': self.order.code},
                self.order.event.settings.mail_text_order_changed,
                {
                    'event': self.order.event.name,
                    'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                        'order': self.order.code,
                        'secret': self.order.secret
                    }),
                    'invoice_name': invoice_name,
                    'invoice_company': invoice_company,
                },
                self.order.event, locale=self.order.locale
            )

    def commit(self):
        if not self._operations:
            # Do nothing
            return
        with transaction.atomic():
            with self.order.event.lock():
                if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
                    raise OrderError(self.error_messages['not_pending_or_paid'])
                self._check_free_to_paid()
                self._check_paid_price_change()
                self._check_quotas()
                self._check_complete_cancel()
                self._perform_operations()
            self._recalculate_total_and_payment_fee()
            self._reissue_invoice()
            self._clear_tickets_cache()
        self._check_paid_to_free()
        self._notify_user()

    def _clear_tickets_cache(self):
        CachedTicket.objects.filter(order_position__order=self.order).delete()

    def _get_payment_provider(self):
        responses = register_payment_providers.send(self.order.event)
        pprov = None
        for rec, response in responses:
            provider = response(self.order.event)
            if provider.identifier == self.order.payment_provider:
                return provider
        if not pprov:
            raise OrderError(error_messages['internal'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def perform_order(self, event: str, payment_provider: str, positions: List[str],
                  email: str=None, locale: str=None, address: int=None, meta_info: dict=None):
    with language(locale):
        try:
            try:
                return _perform_order(event, payment_provider, positions, email, locale, address, meta_info)
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            return OrderError(error_messages['busy'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def cancel_order(self, order: int, user: int=None):
    try:
        try:
            return _cancel_order(order, user)
        except LockTimeoutException:
            self.retry(exc=OrderError(error_messages['busy']))
    except (MaxRetriesExceededError, LockTimeoutException):
        return OrderError(error_messages['busy'])
