import json
import logging
from collections import Counter, namedtuple
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import List, Optional

from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Q, Sum
from django.db.models.functions import Greatest
from django.dispatch import receiver
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now
from django.utils.translation import ugettext as _
from django_scopes import scopes_disabled

from pretix.api.models import OAuthApplication
from pretix.base.email import get_email_context
from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CartPosition, Device, Event, Item, ItemVariation, Order, OrderPayment,
    OrderPosition, Quota, Seat, SeatCategoryMapping, User, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.items import ItemBundle
from pretix.base.models.orders import (
    InvoiceAddress, OrderFee, OrderRefund, generate_position_secret,
    generate_secret,
)
from pretix.base.models.organizer import TeamAPIToken
from pretix.base.models.tax import TaxedPrice
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.services import tickets
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_qualified,
)
from pretix.base.services.locking import LockTimeoutException, NoLockManager
from pretix.base.services.mail import SendMailException
from pretix.base.services.pricing import get_price
from pretix.base.services.tasks import ProfiledEventTask, ProfiledTask
from pretix.base.signals import (
    allow_ticket_download, order_approved, order_canceled, order_changed,
    order_denied, order_expired, order_fee_calculation, order_placed,
    order_split, periodic_task, validate_order,
)
from pretix.celery_app import app
from pretix.helpers.models import modelcopy

error_messages = {
    'unavailable': _('Some of the products you selected were no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected were no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'price_changed': _('The price of some of the items in your cart has changed in the '
                       'meantime. Please see below for details.'),
    'internal': _("An internal error occurred, please try again."),
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
    'some_subevent_not_started': _('The presale period for one of the events in your cart has not yet started. The '
                                   'affected positions have been removed from your cart.'),
    'some_subevent_ended': _('The presale period for one of the events in your cart has ended. The affected '
                             'positions have been removed from your cart.'),
    'seat_invalid': _('One of the seats in your order was invalid, we removed the position from your cart.'),
    'seat_unavailable': _('One of the seats in your order has been taken in the meantime, we removed the position from your cart.'),
}

logger = logging.getLogger(__name__)


def mark_order_paid(*args, **kwargs):
    raise NotImplementedError("This method is no longer supported since pretix 1.17.")


def extend_order(order: Order, new_date: datetime, force: bool=False, user: User=None, auth=None):
    """
    Extends the deadline of an order. If the order is already expired, the quota will be checked to
    see if this is actually still possible. If ``force`` is set to ``True``, the result of this check
    will be ignored.
    """
    if new_date < now():
        raise OrderError(_('The new expiry date needs to be in the future.'))

    def change(was_expired=True):
        order.expires = new_date
        if was_expired:
            order.status = Order.STATUS_PENDING
        order.save(update_fields=['expires'] + (['status'] if was_expired else []))
        order.log_action(
            'pretix.event.order.expirychanged',
            user=user,
            auth=auth,
            data={
                'expires': order.expires,
                'state_change': was_expired
            }
        )
        if was_expired:
            num_invoices = order.invoices.filter(is_cancellation=False).count()
            if num_invoices > 0 and order.invoices.filter(is_cancellation=True).count() >= num_invoices:
                generate_invoice(order)

    if order.status == Order.STATUS_PENDING:
        change(was_expired=False)
    else:
        with order.event.lock() as now_dt:
            is_available = order._is_still_available(now_dt, count_waitinglist=False)
            if is_available is True or force is True:
                change(was_expired=True)
            else:
                raise OrderError(is_available)


@transaction.atomic
def mark_order_refunded(order, user=None, auth=None, api_token=None):
    oautha = auth.pk if isinstance(auth, OAuthApplication) else None
    device = auth.pk if isinstance(auth, Device) else None
    api_token = (api_token.pk if api_token else None) or (auth if isinstance(auth, TeamAPIToken) else None)
    return _cancel_order(
        order.pk, user.pk if user else None, send_mail=False, api_token=api_token, device=device, oauth_application=oautha
    )


def mark_order_expired(order, user=None, auth=None):
    """
    Mark this order as expired. This sets the payment status and returns the order object.
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if isinstance(order, int):
            order = Order.objects.get(pk=order)
        if isinstance(user, int):
            user = User.objects.get(pk=user)
        with order.event.lock():
            order.status = Order.STATUS_EXPIRED
            order.save(update_fields=['status'])

        order.log_action('pretix.event.order.expired', user=user, auth=auth)
        i = order.invoices.filter(is_cancellation=False).last()
        if i:
            generate_cancellation(i)

    order_expired.send(order.event, order=order)
    return order


def approve_order(order, user=None, send_mail: bool=True, auth=None, force=False):
    """
    Mark this order as approved
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if not order.require_approval or not order.status == Order.STATUS_PENDING:
            raise OrderError(_('This order is not pending approval.'))

        order.require_approval = False
        order.set_expires(now(), order.event.subevents.filter(id__in=[p.subevent_id for p in order.positions.all()]))
        order.save(update_fields=['require_approval', 'expires'])

        order.log_action('pretix.event.order.approved', user=user, auth=auth)
        if order.total == Decimal('0.00'):
            p = order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider='free',
                amount=0,
                fee=None
            )
            try:
                p.confirm(send_mail=False, count_waitinglist=False, user=user, auth=auth, ignore_date=True, force=force)
            except Quota.QuotaExceededException:
                raise OrderError(error_messages['unavailable'])

    order_approved.send(order.event, order=order)

    invoice = order.invoices.last()  # Might be generated by plugin already
    if order.event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        if not invoice:
            invoice = generate_invoice(
                order,
                trigger_pdf=not order.event.settings.invoice_email_attachment or not order.email
            )
            # send_mail will trigger PDF generation later

    if send_mail:
        with language(order.locale):
            if order.total == Decimal('0.00'):
                email_template = order.event.settings.mail_text_order_free
                email_subject = _('Order approved and confirmed: %(code)s') % {'code': order.code}
            else:
                email_template = order.event.settings.mail_text_order_approved
                email_subject = _('Order approved and awaiting payment: %(code)s') % {'code': order.code}

            email_context = get_email_context(event=order.event, order=order)
            try:
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_approved', user,
                    invoices=[invoice] if invoice and order.event.settings.invoice_email_attachment else []
                )
            except SendMailException:
                logger.exception('Order approved email could not be sent')

    return order.pk


def deny_order(order, comment='', user=None, send_mail: bool=True, auth=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if not order.require_approval or not order.status == Order.STATUS_PENDING:
            raise OrderError(_('This order is not pending approval.'))

        with order.event.lock():
            order.status = Order.STATUS_CANCELED
            order.save(update_fields=['status'])

        order.log_action('pretix.event.order.denied', user=user, auth=auth, data={
            'comment': comment
        })
        i = order.invoices.filter(is_cancellation=False).last()
        if i:
            generate_cancellation(i)

        for position in order.positions.all():
            if position.voucher:
                Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))

    order_denied.send(order.event, order=order)

    if send_mail:
        email_template = order.event.settings.mail_text_order_denied
        email_context = get_email_context(event=order.event, order=order, comment=comment)
        with language(order.locale):
            email_subject = _('Order denied: %(code)s') % {'code': order.code}
            try:
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_denied', user
                )
            except SendMailException:
                logger.exception('Order denied email could not be sent')

    return order.pk


def _cancel_order(order, user=None, send_mail: bool=True, api_token=None, device=None, oauth_application=None,
                  cancellation_fee=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if isinstance(order, int):
            order = Order.objects.get(pk=order)
        if isinstance(user, int):
            user = User.objects.get(pk=user)
        if isinstance(api_token, int):
            api_token = TeamAPIToken.objects.get(pk=api_token)
        if isinstance(device, int):
            device = Device.objects.get(pk=device)
        if isinstance(oauth_application, int):
            oauth_application = OAuthApplication.objects.get(pk=oauth_application)
        if isinstance(cancellation_fee, str):
            cancellation_fee = Decimal(cancellation_fee)

        if not order.cancel_allowed():
            raise OrderError(_('You cannot cancel this order.'))
        i = order.invoices.filter(is_cancellation=False).last()
        if i:
            generate_cancellation(i)

        if cancellation_fee:
            with order.event.lock():
                for position in order.positions.all():
                    if position.voucher:
                        Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                    position.canceled = True
                    position.save(update_fields=['canceled'])
                for fee in order.fees.all():
                    fee.canceled = True
                    fee.save(update_fields=['canceled'])

                f = OrderFee(
                    fee_type=OrderFee.FEE_TYPE_CANCELLATION,
                    value=cancellation_fee,
                    tax_rule=order.event.settings.tax_rate_default,
                    order=order,
                )
                f._calculate_tax()
                f.save()

                if order.payment_refund_sum < cancellation_fee:
                    raise OrderError(_('The cancellation fee cannot be higher than the payment credit of this order.'))
                order.status = Order.STATUS_PAID
                order.total = f.value
                order.save(update_fields=['status', 'total'])

            if i:
                generate_invoice(order)
        else:
            with order.event.lock():
                order.status = Order.STATUS_CANCELED
                order.save(update_fields=['status'])

            for position in order.positions.all():
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))

        order.log_action('pretix.event.order.canceled', user=user, auth=api_token or oauth_application or device,
                         data={'cancellation_fee': cancellation_fee})

        if send_mail:
            email_template = order.event.settings.mail_text_order_canceled
            with language(order.locale):
                email_context = get_email_context(event=order.event, order=order)
                email_subject = _('Order canceled: %(code)s') % {'code': order.code}
                try:
                    order.send_mail(
                        email_subject, email_template, email_context,
                        'pretix.event.order.email.order_canceled', user
                    )
                except SendMailException:
                    logger.exception('Order canceled email could not be sent')

    order_canceled.send(order.event, order=order)
    return order.pk


class OrderError(LazyLocaleException):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


def _check_date(event: Event, now_dt: datetime):
    if event.presale_start and now_dt < event.presale_start:
        raise OrderError(error_messages['not_started'])
    if event.presale_has_ended:
        raise OrderError(error_messages['ended'])

    if not event.has_subevents:
        tlv = event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if tlv:
            term_last = make_aware(datetime.combine(
                tlv.datetime(event).date(),
                time(hour=23, minute=59, second=59)
            ), event.timezone)
            if term_last < now_dt:
                raise OrderError(error_messages['ended'])


def _check_positions(event: Event, now_dt: datetime, positions: List[CartPosition], address: InvoiceAddress=None):
    err = None
    errargs = None
    _check_date(event, now_dt)

    products_seen = Counter()
    changed_prices = {}
    deleted_positions = set()
    seats_seen = set()

    def delete(cp):
        # Delete a cart position, including parents and children, if applicable
        if cp.is_bundled:
            delete(cp.addon_to)
        else:
            for p in cp.addons.all():
                deleted_positions.add(p.pk)
                p.delete()
            deleted_positions.add(cp.pk)
            cp.delete()

    for i, cp in enumerate(sorted(positions, key=lambda s: -int(s.is_bundled))):
        if cp.pk in deleted_positions:
            continue

        if not cp.item.is_available() or (cp.variation and not cp.variation.active):
            err = err or error_messages['unavailable']
            delete(cp)
            continue
        quotas = list(cp.quotas)

        products_seen[cp.item] += 1
        if cp.item.max_per_order and products_seen[cp.item] > cp.item.max_per_order:
            err = error_messages['max_items_per_product']
            errargs = {'max': cp.item.max_per_order,
                       'product': cp.item.name}
            delete(cp)
            break

        if cp.voucher:
            redeemed_in_carts = CartPosition.objects.filter(
                Q(voucher=cp.voucher) & Q(event=event) & Q(expires__gte=now_dt)
            ).exclude(pk=cp.pk)
            v_avail = cp.voucher.max_usages - cp.voucher.redeemed - redeemed_in_carts.count()
            if v_avail < 1:
                err = err or error_messages['voucher_redeemed']
                delete(cp)
                continue

        if cp.subevent and cp.subevent.presale_start and now_dt < cp.subevent.presale_start:
            err = err or error_messages['some_subevent_not_started']
            delete(cp)
            break

        if cp.subevent:
            tlv = event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
            if tlv:
                term_last = make_aware(datetime.combine(
                    tlv.datetime(cp.subevent).date(),
                    time(hour=23, minute=59, second=59)
                ), event.timezone)
                if term_last < now_dt:
                    err = err or error_messages['some_subevent_ended']
                    delete(cp)
                    break

        if cp.subevent and cp.subevent.presale_has_ended:
            err = err or error_messages['some_subevent_ended']
            delete(cp)
            break

        if (cp.requires_seat and not cp.seat) or (cp.seat and not cp.requires_seat) or (cp.seat and cp.seat.product != cp.item) or cp.seat in seats_seen:
            err = err or error_messages['seat_invalid']
            delete(cp)
            break
        if cp.seat:
            seats_seen.add(cp.seat)

        if cp.item.require_voucher and cp.voucher is None and not cp.is_bundled:
            delete(cp)
            err = err or error_messages['voucher_required']
            break

        if cp.item.hide_without_voucher and (
                cp.voucher is None or not cp.voucher.show_hidden_items or not cp.voucher.applies_to(cp.item, cp.variation)
        ) and not cp.is_bundled:
            delete(cp)
            cp.delete()
            err = error_messages['voucher_required']
            break

        if cp.seat:
            # Unlike quotas (which we blindly trust as long as the position is not expired), we check seats every time, since we absolutely
            # can not overbook a seat.
            if not cp.seat.is_available(ignore_cart=cp) or cp.seat.blocked:
                err = err or error_messages['seat_unavailable']
                cp.delete()
                continue

        if cp.expires >= now_dt and not cp.voucher:
            # Other checks are not necessary
            continue

        if cp.is_bundled:
            try:
                bundle = cp.addon_to.item.bundles.get(bundled_item=cp.item, bundled_variation=cp.variation)
                bprice = bundle.designated_price or 0
            except ItemBundle.DoesNotExist:
                bprice = cp.price
            price = get_price(cp.item, cp.variation, cp.voucher, bprice, cp.subevent, custom_price_is_net=False,
                              invoice_address=address, force_custom_price=True)
            changed_prices[cp.pk] = bprice
        else:
            bundled_sum = 0
            if not cp.addon_to_id:
                for bundledp in cp.addons.all():
                    if bundledp.is_bundled:
                        bundled_sum += changed_prices.get(bundledp.pk, bundledp.price)

            price = get_price(cp.item, cp.variation, cp.voucher, cp.price, cp.subevent, custom_price_is_net=False,
                              addon_to=cp.addon_to, invoice_address=address, bundled_sum=bundled_sum)

        if price is False or len(quotas) == 0:
            err = err or error_messages['unavailable']
            delete(cp)
            continue

        if cp.voucher:
            if cp.voucher.valid_until and cp.voucher.valid_until < now_dt:
                err = err or error_messages['voucher_expired']
                delete(cp)
                continue

        if price.gross != cp.price and not (cp.item.free_price and cp.price > price.gross):
            cp.price = price.gross
            cp.includes_tax = bool(price.rate)
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
            cp.expires = now_dt + timedelta(
                minutes=event.settings.get('reservation_time', as_type=int))
            cp.save()
        else:
            # Sorry, can't let you keep that!
            delete(cp)
    if err:
        raise OrderError(err, errargs)


def _get_fees(positions: List[CartPosition], payment_provider: BasePaymentProvider, address: InvoiceAddress,
              meta_info: dict, event: Event):
    fees = []
    total = sum([c.price for c in positions])

    for recv, resp in order_fee_calculation.send(sender=event, invoice_address=address, total=total,
                                                 meta_info=meta_info, positions=positions):
        if resp:
            fees += resp

    total += sum(f.value for f in fees)
    if payment_provider:
        payment_fee = payment_provider.calculate_fee(total)
    else:
        payment_fee = 0
    pf = None
    if payment_fee:
        pf = OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=payment_fee,
                      internal_type=payment_provider.identifier)
        fees.append(pf)

    return fees, pf


def _create_order(event: Event, email: str, positions: List[CartPosition], now_dt: datetime,
                  payment_provider: BasePaymentProvider, locale: str=None, address: InvoiceAddress=None,
                  meta_info: dict=None, sales_channel: str='web'):
    fees, pf = _get_fees(positions, payment_provider, address, meta_info, event)
    total = sum([c.price for c in positions]) + sum([c.value for c in fees])
    p = None

    with transaction.atomic():
        order = Order(
            status=Order.STATUS_PENDING,
            event=event,
            email=email,
            datetime=now_dt,
            locale=locale,
            total=total,
            testmode=event.testmode,
            meta_info=json.dumps(meta_info or {}),
            require_approval=any(p.item.require_approval for p in positions),
            sales_channel=sales_channel
        )
        order.set_expires(now_dt, event.subevents.filter(id__in=[p.subevent_id for p in positions]))
        order.save()

        if address:
            if address.order is not None:
                address.pk = None
            address.order = order
            address.save()

            order.save()

        for fee in fees:
            fee.order = order
            fee._calculate_tax()
            if fee.tax_rule and not fee.tax_rule.pk:
                fee.tax_rule = None  # TODO: deprecate
            fee.save()

        if payment_provider and not order.require_approval:
            p = order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider=payment_provider.identifier,
                amount=total,
                fee=pf
            )

        OrderPosition.transform_cart_positions(positions, order)
        order.log_action('pretix.event.order.placed')
        if order.require_approval:
            order.log_action('pretix.event.order.placed.require_approval')
        if meta_info:
            for msg in meta_info.get('confirm_messages', []):
                order.log_action('pretix.event.order.consent', data={'msg': msg})

    order_placed.send(event, order=order)
    return order, p


def _order_placed_email(event: Event, order: Order, pprov: BasePaymentProvider, email_template, log_entry: str,
                        invoice, payment: OrderPayment):
    email_context = get_email_context(event=event, order=order, payment=payment if pprov else None)
    email_subject = _('Your order: %(code)s') % {'code': order.code}
    try:
        order.send_mail(
            email_subject, email_template, email_context,
            log_entry,
            invoices=[invoice] if invoice and event.settings.invoice_email_attachment else [],
            attach_tickets=True
        )
    except SendMailException:
        logger.exception('Order received email could not be sent')


def _order_placed_email_attendee(event: Event, order: Order, position: OrderPosition, email_template, log_entry: str):
    email_context = get_email_context(event=event, order=order, position=position)
    email_subject = _('Your event registration: %(code)s') % {'code': order.code}

    try:
        order.send_mail(
            email_subject, email_template, email_context,
            log_entry,
            invoices=[],
            attach_tickets=True,
            position=position
        )
    except SendMailException:
        logger.exception('Order received email could not be sent to attendee')


def _perform_order(event: Event, payment_provider: str, position_ids: List[str],
                   email: str, locale: str, address: int, meta_info: dict=None, sales_channel: str='web'):
    if payment_provider:
        pprov = event.get_payment_providers().get(payment_provider)
        if not pprov:
            raise OrderError(error_messages['internal'])
    else:
        pprov = None

    if email == settings.PRETIX_EMAIL_NONE_VALUE:
        email = None

    addr = None
    if address is not None:
        try:
            with scopes_disabled():
                addr = InvoiceAddress.objects.get(pk=address)
        except InvoiceAddress.DoesNotExist:
            pass

    positions = CartPosition.objects.annotate(
        requires_seat=Exists(
            SeatCategoryMapping.objects.filter(
                Q(product=OuterRef('item'))
                & (Q(subevent=OuterRef('subevent')) if event.has_subevents else Q(subevent__isnull=True))
            )
        )
    ).filter(
        id__in=position_ids, event=event
    )

    validate_order.send(event, payment_provider=pprov, email=email, positions=positions,
                        locale=locale, invoice_address=addr, meta_info=meta_info)

    lockfn = NoLockManager
    locked = False
    if positions.filter(Q(voucher__isnull=False) | Q(expires__lt=now() + timedelta(minutes=2)) | Q(seat__isnull=False)).exists():
        # Performance optimization: If no voucher is used and no cart position is dangerously close to its expiry date,
        # creating this order shouldn't be prone to any race conditions and we don't need to lock the event.
        locked = True
        lockfn = event.lock

    with lockfn() as now_dt:
        positions = list(positions.select_related('item', 'variation', 'subevent', 'seat', 'addon_to').prefetch_related('addons'))
        if len(positions) == 0:
            raise OrderError(error_messages['empty'])
        if len(position_ids) != len(positions):
            raise OrderError(error_messages['internal'])
        _check_positions(event, now_dt, positions, address=addr)
        order, payment = _create_order(event, email, positions, now_dt, pprov,
                                       locale=locale, address=addr, meta_info=meta_info, sales_channel=sales_channel)

        free_order_flow = payment and payment_provider == 'free' and order.total == Decimal('0.00') and not order.require_approval
        if free_order_flow:
            try:
                payment.confirm(send_mail=False, lock=not locked)
            except Quota.QuotaExceededException:
                pass

    invoice = order.invoices.last()  # Might be generated by plugin already
    if event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        if not invoice:
            invoice = generate_invoice(
                order,
                trigger_pdf=not event.settings.invoice_email_attachment or not order.email
            )
            # send_mail will trigger PDF generation later

    if order.email:
        if order.require_approval:
            email_template = event.settings.mail_text_order_placed_require_approval
            log_entry = 'pretix.event.order.email.order_placed_require_approval'

            email_attendees = False
        elif free_order_flow:
            email_template = event.settings.mail_text_order_free
            log_entry = 'pretix.event.order.email.order_free'

            email_attendees = event.settings.mail_send_order_free_attendee
            email_attendees_template = event.settings.mail_text_order_free_attendee
        else:
            email_template = event.settings.mail_text_order_placed
            log_entry = 'pretix.event.order.email.order_placed'

            email_attendees = event.settings.mail_send_order_placed_attendee
            email_attendees_template = event.settings.mail_text_order_placed_attendee

        _order_placed_email(event, order, pprov, email_template, log_entry, invoice, payment)
        if email_attendees:
            for p in order.positions.all():
                if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                    _order_placed_email_attendee(event, order, p, email_attendees_template, log_entry)

    return order.id


@receiver(signal=periodic_task)
@scopes_disabled()
def expire_orders(sender, **kwargs):
    eventcache = {}

    for o in Order.objects.filter(expires__lt=now(), status=Order.STATUS_PENDING,
                                  require_approval=False).select_related('event'):
        expire = eventcache.get(o.event.pk, None)
        if expire is None:
            expire = o.event.settings.get('payment_term_expire_automatically', as_type=bool)
            eventcache[o.event.pk] = expire
        if expire:
            mark_order_expired(o)


@receiver(signal=periodic_task)
@scopes_disabled()
def send_expiry_warnings(sender, **kwargs):
    eventcache = {}
    today = now().replace(hour=0, minute=0, second=0)

    for o in Order.objects.filter(
        expires__gte=today, expiry_reminder_sent=False, status=Order.STATUS_PENDING,
        datetime__lte=now() - timedelta(hours=2), require_approval=False
    ).only('pk'):
        with transaction.atomic():
            o = Order.objects.select_related('event').select_for_update().get(pk=o.pk)
            if o.status != Order.STATUS_PENDING or o.expiry_reminder_sent:
                # Race condition
                continue
            eventsettings = eventcache.get(o.event.pk, None)
            if eventsettings is None:
                eventsettings = o.event.settings
                eventcache[o.event.pk] = eventsettings

            days = eventsettings.get('mail_days_order_expire_warning', as_type=int)
            if days and (o.expires - today).days <= days:
                with language(o.locale):
                    o.expiry_reminder_sent = True
                    o.save(update_fields=['expiry_reminder_sent'])
                    email_template = eventsettings.mail_text_order_expire_warning
                    email_context = get_email_context(event=o.event, order=o)
                    if eventsettings.payment_term_expire_automatically:
                        email_subject = _('Your order is about to expire: %(code)s') % {'code': o.code}
                    else:
                        email_subject = _('Your order is pending payment: %(code)s') % {'code': o.code}

                    try:
                        o.send_mail(
                            email_subject, email_template, email_context,
                            'pretix.event.order.email.expire_warning_sent'
                        )
                    except SendMailException:
                        logger.exception('Reminder email could not be sent')


@receiver(signal=periodic_task)
@scopes_disabled()
def send_download_reminders(sender, **kwargs):
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)

    for e in Event.objects.filter(date_from__gte=today):

        days = e.settings.get('mail_days_download_reminder', as_type=int)
        if days is None:
            continue

        reminder_date = (e.date_from - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

        if now() < reminder_date:
            continue
        for o in e.orders.filter(status=Order.STATUS_PAID, download_reminder_sent=False, datetime__lte=now() - timedelta(hours=2)).only('pk'):
            with transaction.atomic():
                o = Order.objects.select_related('event').select_for_update().get(pk=o.pk)
                if o.download_reminder_sent:
                    # Race condition
                    continue
                if not all([r for rr, r in allow_ticket_download.send(e, order=o)]):
                    continue

                with language(o.locale):
                    o.download_reminder_sent = True
                    o.save(update_fields=['download_reminder_sent'])
                    email_template = e.settings.mail_text_download_reminder
                    email_context = get_email_context(event=e, order=o)
                    email_subject = _('Your ticket is ready for download: %(code)s') % {'code': o.code}
                    try:
                        o.send_mail(
                            email_subject, email_template, email_context,
                            'pretix.event.order.email.download_reminder_sent',
                            attach_tickets=True
                        )
                    except SendMailException:
                        logger.exception('Reminder email could not be sent')

                    if e.settings.mail_send_download_reminder_attendee:
                        for p in o.positions.all():
                            if p.addon_to_id is None and p.attendee_email and p.attendee_email != o.email:
                                email_template = e.settings.mail_text_download_reminder_attendee
                                email_context = get_email_context(event=e, order=o, position=p)
                                try:
                                    o.send_mail(
                                        email_subject, email_template, email_context,
                                        'pretix.event.order.email.download_reminder_sent',
                                        attach_tickets=True, position=p
                                    )
                                except SendMailException:
                                    logger.exception('Reminder email could not be sent to attendee')


def notify_user_changed_order(order, user=None, auth=None):
    with language(order.locale):
        email_template = order.event.settings.mail_text_order_changed
        email_context = get_email_context(event=order.event, order=order)
        email_subject = _('Your order has been changed: %(code)s') % {'code': order.code}
        try:
            order.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.order_changed', user, auth=auth
            )
        except SendMailException:
            logger.exception('Order changed email could not be sent')


class OrderChangeManager:
    error_messages = {
        'product_without_variation': _('You need to select a variation of the product.'),
        'quota': _('The quota {name} does not have enough capacity left to perform the operation.'),
        'quota_missing': _('There is no quota defined that allows this operation.'),
        'product_invalid': _('The selected product is not active or has no price set.'),
        'complete_cancel': _('This operation would leave the order empty. Please cancel the order itself instead.'),
        'not_pending_or_paid': _('Only pending or paid orders can be changed.'),
        'paid_to_free_exceeded': _('This operation would make the order free and therefore immediately paid, however '
                                   'no quota is available.'),
        'addon_to_required': _('This is an add-on product, please select the base position it should be added to.'),
        'addon_invalid': _('The selected base position does not allow you to add this product as an add-on.'),
        'subevent_required': _('You need to choose a subevent for the new position.'),
        'seat_unavailable': _('The selected seat "{seat}" is not available.'),
        'seat_subevent_mismatch': _('You selected seat "{seat}" for a date that does not match the selected ticket date. Please choose a seat again.'),
        'seat_required': _('The selected product requires you to select a seat.'),
        'seat_forbidden': _('The selected product does not allow to select a seat.'),
    }
    ItemOperation = namedtuple('ItemOperation', ('position', 'item', 'variation'))
    SubeventOperation = namedtuple('SubeventOperation', ('position', 'subevent'))
    SeatOperation = namedtuple('SubeventOperation', ('position', 'seat'))
    PriceOperation = namedtuple('PriceOperation', ('position', 'price'))
    CancelOperation = namedtuple('CancelOperation', ('position',))
    AddOperation = namedtuple('AddOperation', ('item', 'variation', 'price', 'addon_to', 'subevent', 'seat'))
    SplitOperation = namedtuple('SplitOperation', ('position',))
    RegenerateSecretOperation = namedtuple('RegenerateSecretOperation', ('position',))

    def __init__(self, order: Order, user=None, auth=None, notify=True, reissue_invoice=True):
        self.order = order
        self.user = user
        self.auth = auth
        self.event = order.event
        self.split_order = None
        self.reissue_invoice = reissue_invoice
        self._committed = False
        self._totaldiff = 0
        self._quotadiff = Counter()
        self._seatdiff = Counter()
        self._operations = []
        self.notify = notify
        self._invoice_dirty = False

    def change_item(self, position: OrderPosition, item: Item, variation: Optional[ItemVariation]):
        if (not variation and item.has_variations) or (variation and variation.item_id != item.pk):
            raise OrderError(self.error_messages['product_without_variation'])

        new_quotas = (variation.quotas.filter(subevent=position.subevent)
                      if variation else item.quotas.filter(subevent=position.subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.ItemOperation(position, item, variation))

    def change_seat(self, position: OrderPosition, seat: Seat):
        if position.seat:
            self._seatdiff.subtract([position.seat])
        if seat:
            self._seatdiff.update([seat])
        self._operations.append(self.SeatOperation(position, seat))

    def change_subevent(self, position: OrderPosition, subevent: SubEvent):
        price = get_price(position.item, position.variation, voucher=position.voucher, subevent=subevent,
                          invoice_address=self._invoice_address)

        if price is None:  # NOQA
            raise OrderError(self.error_messages['product_invalid'])

        new_quotas = (position.variation.quotas.filter(subevent=subevent)
                      if position.variation else position.item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.SubeventOperation(position, subevent))

    def regenerate_secret(self, position: OrderPosition):
        self._operations.append(self.RegenerateSecretOperation(position))

    def change_price(self, position: OrderPosition, price: Decimal):
        price = position.item.tax(price, base_price_is='gross')

        self._totaldiff += price.gross - position.price

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00') or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._operations.append(self.PriceOperation(position, price))

    def recalculate_taxes(self):
        positions = self.order.positions.select_related('item', 'item__tax_rule')
        ia = self._invoice_address
        for pos in positions:
            if not pos.item.tax_rule:
                continue
            if not pos.price:
                continue

            charge_tax = pos.item.tax_rule.tax_applicable(ia)
            if pos.tax_value and not charge_tax:
                net_price = pos.price - pos.tax_value
                price = TaxedPrice(gross=net_price, net=net_price, tax=Decimal('0.00'), rate=Decimal('0.00'), name='')
                if price.gross != pos.price:
                    self._totaldiff += price.gross - pos.price
                    self._operations.append(self.PriceOperation(pos, price))
            elif charge_tax and not pos.tax_value:
                price = pos.item.tax(pos.price, base_price_is='net')
                if price.gross != pos.price:
                    self._totaldiff += price.gross - pos.price
                    self._operations.append(self.PriceOperation(pos, price))

    def cancel(self, position: OrderPosition):
        self._totaldiff += -position.price
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.CancelOperation(position))
        if position.seat:
            self._seatdiff.subtract([position.seat])

        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

    def add_position(self, item: Item, variation: ItemVariation, price: Decimal, addon_to: Order = None,
                     subevent: SubEvent = None, seat: Seat = None):
        if price is None:
            price = get_price(item, variation, subevent=subevent, invoice_address=self._invoice_address)
        else:
            if item.tax_rule and item.tax_rule.tax_applicable(self._invoice_address):
                price = item.tax(price, base_price_is='gross')
            else:
                price = TaxedPrice(gross=price, net=price, tax=Decimal('0.00'), rate=Decimal('0.00'), name='')

        if price is None:
            raise OrderError(self.error_messages['product_invalid'])
        if not addon_to and item.category and item.category.is_addon:
            raise OrderError(self.error_messages['addon_to_required'])
        if addon_to:
            if not item.category or item.category_id not in addon_to.item.addons.values_list('addon_category', flat=True):
                raise OrderError(self.error_messages['addon_invalid'])
        if self.order.event.has_subevents and not subevent:
            raise OrderError(self.error_messages['subevent_required'])

        seated = item.seat_category_mappings.filter(subevent=subevent).exists()
        if seated and not seat:
            raise OrderError(self.error_messages['seat_required'])
        elif not seated and seat:
            raise OrderError(self.error_messages['seat_forbidden'])
        if seat and subevent and seat.subevent_id != subevent:
            raise OrderError(self.error_messages['seat_subevent_mismatch'].format(seat=seat.name))

        new_quotas = (variation.quotas.filter(subevent=subevent)
                      if variation else item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00'):
            self._invoice_dirty = True

        self._totaldiff += price.gross
        self._quotadiff.update(new_quotas)
        if seat:
            self._seatdiff.update([seat])
        self._operations.append(self.AddOperation(item, variation, price, addon_to, subevent, seat))

    def split(self, position: OrderPosition):
        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._operations.append(self.SplitOperation(position))

    def _check_seats(self):
        for seat, diff in self._seatdiff.items():
            if diff <= 0:
                continue
            if not seat.is_available() or diff > 1:
                raise OrderError(self.error_messages['seat_unavailable'].format(seat=seat.name))

        if self.event.has_subevents:
            state = {}
            for p in self.order.positions.all():
                state[p] = {'seat': p.seat, 'subevent': p.subevent}
            for op in self._operations:
                if isinstance(op, self.SeatOperation):
                    state[op.position]['seat'] = op.seat
                elif isinstance(op, self.SubeventOperation):
                    state[op.position]['subevent'] = op.subevent
            for v in state.values():
                if v['seat'] and v['seat'].subevent_id != v['subevent'].pk:
                    raise OrderError(self.error_messages['seat_subevent_mismatch'].format(seat=v['seat'].name))

    def _check_quotas(self):
        for quota, diff in self._quotadiff.items():
            if diff <= 0:
                continue
            avail = quota.availability()
            if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < diff):
                raise OrderError(self.error_messages['quota'].format(name=quota.name))

    def _check_paid_price_change(self):
        if self.order.status == Order.STATUS_PAID and self._totaldiff > 0:
            if self.order.pending_sum > Decimal('0.00'):
                self.order.status = Order.STATUS_PENDING
                self.order.set_expires(
                    now(),
                    self.order.event.subevents.filter(id__in=self.order.positions.values_list('subevent_id', flat=True))
                )
                self.order.save()
        elif self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and self._totaldiff < 0:
            if self.order.pending_sum <= Decimal('0.00') and not self.order.require_approval:
                self.order.status = Order.STATUS_PAID
                self.order.save()
            elif self.open_payment:
                self.open_payment.state = OrderPayment.PAYMENT_STATE_CANCELED
                self.open_payment.save()
                self.order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': self.open_payment.local_id,
                    'provider': self.open_payment.provider,
                }, user=self.user, auth=self.auth)
        elif self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and self._totaldiff > 0:
            if self.open_payment:
                self.open_payment.state = OrderPayment.PAYMENT_STATE_CANCELED
                self.open_payment.save()
                self.order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': self.open_payment.local_id,
                    'provider': self.open_payment.provider,
                }, user=self.user, auth=self.auth)

    def _check_paid_to_free(self):
        if self.order.total == 0 and (self._totaldiff < 0 or (self.split_order and self.split_order.total > 0)) and not self.order.require_approval:
            # if the order becomes free, mark it paid using the 'free' provider
            # this could happen if positions have been made cheaper or removed (_totaldiff < 0)
            # or positions got split off to a new order (split_order with positive total)
            p = self.order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider='free',
                amount=0,
                fee=None
            )
            try:
                p.confirm(send_mail=False, count_waitinglist=False, user=self.user, auth=self.auth)
            except Quota.QuotaExceededException:
                raise OrderError(self.error_messages['paid_to_free_exceeded'])

        if self.split_order and self.split_order.total == 0 and not self.split_order.require_approval:
            p = self.split_order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider='free',
                amount=0,
                fee=None
            )
            try:
                p.confirm(send_mail=False, count_waitinglist=False, user=self.user, auth=self.auth)
            except Quota.QuotaExceededException:
                raise OrderError(self.error_messages['paid_to_free_exceeded'])

    def _perform_operations(self):
        nextposid = self.order.all_positions.aggregate(m=Max('positionid'))['m'] + 1
        split_positions = []

        for op in self._operations:
            if isinstance(op, self.ItemOperation):
                self.order.log_action('pretix.event.order.changed.item', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'new_item': op.item.pk,
                    'new_variation': op.variation.pk if op.variation else None,
                    'old_price': op.position.price,
                    'addon_to': op.position.addon_to_id,
                    'new_price': op.position.price
                })
                op.position.item = op.item
                op.position.variation = op.variation
                op.position._calculate_tax()
                op.position.save()
            elif isinstance(op, self.SeatOperation):
                self.order.log_action('pretix.event.order.changed.seat', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_seat': op.position.seat.name if op.position.seat else "-",
                    'new_seat': op.seat.name if op.seat else "-",
                    'old_seat_id': op.position.seat.pk if op.position.seat else None,
                    'new_seat_id': op.seat.pk if op.seat else None,
                })
                op.position.seat = op.seat
                op.position.save()
            elif isinstance(op, self.SubeventOperation):
                self.order.log_action('pretix.event.order.changed.subevent', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_subevent': op.position.subevent.pk,
                    'new_subevent': op.subevent.pk,
                    'old_price': op.position.price,
                    'new_price': op.position.price
                })
                op.position.subevent = op.subevent
                op.position.save()
            elif isinstance(op, self.PriceOperation):
                self.order.log_action('pretix.event.order.changed.price', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_price': op.position.price,
                    'addon_to': op.position.addon_to_id,
                    'new_price': op.price.gross
                })
                op.position.price = op.price.gross
                op.position._calculate_tax()
                op.position.save()
            elif isinstance(op, self.CancelOperation):
                for opa in op.position.addons.all():
                    self.order.log_action('pretix.event.order.changed.cancel', user=self.user, auth=self.auth, data={
                        'position': opa.pk,
                        'positionid': opa.positionid,
                        'old_item': opa.item.pk,
                        'old_variation': opa.variation.pk if opa.variation else None,
                        'addon_to': opa.addon_to_id,
                        'old_price': opa.price,
                    })
                    opa.canceled = True
                    if opa.voucher:
                        Voucher.objects.filter(pk=opa.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                    opa.save(update_fields=['canceled'])
                self.order.log_action('pretix.event.order.changed.cancel', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_item': op.position.item.pk,
                    'old_variation': op.position.variation.pk if op.position.variation else None,
                    'old_price': op.position.price,
                    'addon_to': None,
                })
                op.position.canceled = True
                if op.position.voucher:
                    Voucher.objects.filter(pk=op.position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                op.position.save(update_fields=['canceled'])
            elif isinstance(op, self.AddOperation):
                pos = OrderPosition.objects.create(
                    item=op.item, variation=op.variation, addon_to=op.addon_to,
                    price=op.price.gross, order=self.order, tax_rate=op.price.rate,
                    tax_value=op.price.tax, tax_rule=op.item.tax_rule,
                    positionid=nextposid, subevent=op.subevent, seat=op.seat
                )
                nextposid += 1
                self.order.log_action('pretix.event.order.changed.add', user=self.user, auth=self.auth, data={
                    'position': pos.pk,
                    'item': op.item.pk,
                    'variation': op.variation.pk if op.variation else None,
                    'addon_to': op.addon_to.pk if op.addon_to else None,
                    'price': op.price.gross,
                    'positionid': pos.positionid,
                    'subevent': op.subevent.pk if op.subevent else None,
                    'seat': op.seat.pk if op.seat else None,
                })
            elif isinstance(op, self.SplitOperation):
                split_positions.append(op.position)
            elif isinstance(op, self.RegenerateSecretOperation):
                op.position.secret = generate_position_secret()
                op.position.save()
                tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                             'order': self.order.pk})
                self.order.log_action('pretix.event.order.changed.secret', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                })

        if split_positions:
            self.split_order = self._create_split_order(split_positions)

    def _create_split_order(self, split_positions):
        split_order = Order.objects.get(pk=self.order.pk)
        split_order.pk = None
        split_order.code = None
        split_order.datetime = now()
        split_order.secret = generate_secret()
        split_order.require_approval = self.order.require_approval and any(p.item.require_approval for p in split_positions)
        split_order.save()
        split_order.log_action('pretix.event.order.changed.split_from', user=self.user, auth=self.auth, data={
            'original_order': self.order.code
        })

        for op in split_positions:
            self.order.log_action('pretix.event.order.changed.split', user=self.user, auth=self.auth, data={
                'position': op.pk,
                'positionid': op.positionid,
                'old_item': op.item.pk,
                'old_variation': op.variation.pk if op.variation else None,
                'old_price': op.price,
                'new_order': split_order.code,
            })
            op.order = split_order
            op.secret = generate_position_secret()
            op.save()

        try:
            ia = modelcopy(self.order.invoice_address)
            ia.pk = None
            ia.order = split_order
            ia.save()
        except InvoiceAddress.DoesNotExist:
            pass

        split_order.total = sum([p.price for p in split_positions if not p.canceled])

        for fee in self.order.fees.exclude(fee_type=OrderFee.FEE_TYPE_PAYMENT):
            new_fee = modelcopy(fee)
            new_fee.pk = None
            new_fee.order = split_order
            split_order.total += new_fee.value
            new_fee.save()

        if split_order.total != Decimal('0.00') and self.order.status != Order.STATUS_PAID:
            pp = self._get_payment_provider()
            if pp:
                payment_fee = pp.calculate_fee(split_order.total)
            else:
                payment_fee = Decimal('0.00')
            fee = split_order.fees.get_or_create(fee_type=OrderFee.FEE_TYPE_PAYMENT, defaults={'value': 0})[0]
            fee.value = payment_fee
            fee._calculate_tax()
            if payment_fee != 0:
                fee.save()
            elif fee.pk:
                fee.delete()
            split_order.total += fee.value

        split_order.save()

        if split_order.status == Order.STATUS_PAID:
            split_order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=split_order.total,
                payment_date=now(),
                provider='offsetting',
                info=json.dumps({'orders': [self.order.code]})
            )
            self.order.refunds.create(
                state=OrderRefund.REFUND_STATE_DONE,
                amount=split_order.total,
                execution_date=now(),
                provider='offsetting',
                info=json.dumps({'orders': [split_order.code]})
            )

        if split_order.total != Decimal('0.00') and self.order.invoices.filter(is_cancellation=False).last():
            generate_invoice(split_order)

        order_split.send(sender=self.order.event, original=self.order, split_order=split_order)
        return split_order

    @cached_property
    def open_payment(self):
        lp = self.order.payments.last()
        if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED,
                                   OrderPayment.PAYMENT_STATE_REFUNDED):
            return lp

    @cached_property
    def completed_payment_sum(self):
        payment_sum = self.order.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.order.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT, OrderRefund.REFUND_STATE_DONE)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        return payment_sum - refund_sum

    def _recalculate_total_and_payment_fee(self):
        total = sum([p.price for p in self.order.positions.all()]) + sum([f.value for f in self.order.fees.all()])
        payment_fee = Decimal('0.00')
        if self.open_payment:
            current_fee = Decimal('0.00')
            fee = None
            if self.open_payment.fee:
                fee = self.open_payment.fee
                current_fee = self.open_payment.fee.value
            total -= current_fee

            if self.order.pending_sum - current_fee != 0:
                prov = self.open_payment.payment_provider
                if prov:
                    payment_fee = prov.calculate_fee(total - self.completed_payment_sum)

            if payment_fee:
                fee = fee or OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, order=self.order)
                fee.value = payment_fee
                fee._calculate_tax()
                fee.save()
                if not self.open_payment.fee:
                    self.open_payment.fee = fee
                    self.open_payment.save(update_fields=['fee'])
            elif fee:
                fee.delete()

        self.order.total = total + payment_fee
        self.order.save()

    def _payment_fee_diff(self):
        total = self.order.total + self._totaldiff
        if self.open_payment:
            current_fee = Decimal('0.00')
            if self.open_payment and self.open_payment.fee:
                current_fee = self.open_payment.fee.value
            total -= current_fee

            # Do not change payment fees of paid orders
            payment_fee = Decimal('0.00')
            if self.order.pending_sum - current_fee != 0:
                prov = self.open_payment.payment_provider
                if prov:
                    payment_fee = prov.calculate_fee(total - self.completed_payment_sum)

                self._totaldiff += payment_fee - current_fee

    def _reissue_invoice(self):
        i = self.order.invoices.filter(is_cancellation=False).last()
        if self.reissue_invoice and i and self._invoice_dirty:
            generate_cancellation(i)
            generate_invoice(self.order)

    def _check_complete_cancel(self):
        cancels = len([o for o in self._operations if isinstance(o, (self.CancelOperation, self.SplitOperation))])
        adds = len([o for o in self._operations if isinstance(o, self.AddOperation)])
        if self.order.positions.count() - cancels + adds < 1:
            raise OrderError(self.error_messages['complete_cancel'])

    @property
    def _invoice_address(self):
        try:
            return self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            return None

    def commit(self, check_quotas=True):
        if self._committed:
            # an order change can only be committed once
            raise OrderError(error_messages['internal'])
        self._committed = True

        if not self._operations:
            # Do nothing
            return

        # finally, incorporate difference in payment fees
        self._payment_fee_diff()

        with transaction.atomic():
            with self.order.event.lock():
                if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
                    raise OrderError(self.error_messages['not_pending_or_paid'])
                if check_quotas:
                    self._check_quotas()
                self._check_seats()
                self._check_complete_cancel()
                self._perform_operations()
            self._recalculate_total_and_payment_fee()
            self._reissue_invoice()
            self._clear_tickets_cache()
            self.order.touch()
        self._check_paid_price_change()
        self._check_paid_to_free()

        if self.notify:
            notify_user_changed_order(self.order, self.user, self.auth)
            if self.split_order:
                notify_user_changed_order(self.split_order, self.user, self.auth)

        order_changed.send(self.order.event, order=self.order)

    def _clear_tickets_cache(self):
        tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                     'order': self.order.pk})
        if self.split_order:
            tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                         'order': self.split_order.pk})

    def _get_payment_provider(self):
        lp = self.order.payments.last()
        if not lp:
            return None
        pprov = lp.payment_provider
        if not pprov:
            return None
        return pprov


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def perform_order(self, event: Event, payment_provider: str, positions: List[str],
                  email: str=None, locale: str=None, address: int=None, meta_info: dict=None,
                  sales_channel: str='web'):
    with language(locale):
        try:
            try:
                return _perform_order(event, payment_provider, positions, email, locale, address, meta_info,
                                      sales_channel)
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise OrderError(str(error_messages['busy']))


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
@scopes_disabled()
def cancel_order(self, order: int, user: int=None, send_mail: bool=True, api_token=None, oauth_application=None,
                 device=None, cancellation_fee=None, try_auto_refund=False):
    try:
        try:
            ret = _cancel_order(order, user, send_mail, api_token, device, oauth_application,
                                cancellation_fee)
            if try_auto_refund:
                notify_admin = False
                error = False
                order = Order.objects.get(pk=order)
                refund_amount = order.pending_sum * -1
                proposals = order.propose_auto_refunds(refund_amount)
                can_auto_refund = sum(proposals.values()) == refund_amount
                if can_auto_refund:
                    for p, value in proposals.items():
                        with transaction.atomic():
                            r = order.refunds.create(
                                payment=p,
                                source=OrderRefund.REFUND_SOURCE_BUYER,
                                state=OrderRefund.REFUND_STATE_CREATED,
                                amount=value,
                                provider=p.provider
                            )
                            order.log_action('pretix.event.order.refund.created', {
                                'local_id': r.local_id,
                                'provider': r.provider,
                            })

                        try:
                            r.payment_provider.execute_refund(r)
                        except PaymentException as e:
                            with transaction.atomic():
                                r.state = OrderRefund.REFUND_STATE_FAILED
                                r.save()
                                order.log_action('pretix.event.order.refund.failed', {
                                    'local_id': r.local_id,
                                    'provider': r.provider,
                                    'error': str(e)
                                })
                            error = True
                            notify_admin = True
                        else:
                            if r.state != OrderRefund.REFUND_STATE_DONE:
                                notify_admin = True
                elif refund_amount != Decimal('0.00'):
                    notify_admin = True

                if notify_admin:
                    order.log_action('pretix.event.order.refund.requested')
                if error:
                    raise OrderError(
                        _('There was an error while trying to send the money back to you. Please contact the event organizer for further information.')
                    )
            return ret
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise OrderError(error_messages['busy'])


def change_payment_provider(order: Order, payment_provider, amount=None, new_payment=None, create_log=True,
                            recreate_invoices=True):
    oldtotal = order.total
    e = OrderPayment.objects.filter(fee=OuterRef('pk'), state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED,
                                                                   OrderPayment.PAYMENT_STATE_REFUNDED))
    open_fees = list(
        order.fees.annotate(has_p=Exists(e)).filter(
            Q(fee_type=OrderFee.FEE_TYPE_PAYMENT) & ~Q(has_p=True)
        )
    )
    if open_fees:
        fee = open_fees[0]
        if len(open_fees) > 1:
            for f in open_fees[1:]:
                f.delete()
    else:
        fee = OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.00'), order=order)
    old_fee = fee.value

    new_fee = payment_provider.calculate_fee(
        order.pending_sum - old_fee if amount is None else amount
    )
    with transaction.atomic():
        if new_fee:
            fee.value = new_fee
            fee.internal_type = payment_provider.identifier
            fee._calculate_tax()
            fee.save()
        else:
            if fee.pk:
                fee.delete()
            fee = None

    open_payment = None
    if new_payment:
        lp = order.payments.exclude(pk=new_payment.pk).last()
    else:
        lp = order.payments.last()
    if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED):
        open_payment = lp

    if open_payment and open_payment.state in (OrderPayment.PAYMENT_STATE_PENDING,
                                               OrderPayment.PAYMENT_STATE_CREATED):
        open_payment.state = OrderPayment.PAYMENT_STATE_CANCELED
        open_payment.save(update_fields=['state'])

    order.total = (order.positions.aggregate(sum=Sum('price'))['sum'] or 0) + (order.fees.aggregate(sum=Sum('value'))['sum'] or 0)
    order.save(update_fields=['total'])

    if not new_payment:
        new_payment = order.payments.create(
            state=OrderPayment.PAYMENT_STATE_CREATED,
            provider=payment_provider.identifier,
            amount=order.pending_sum,
            fee=fee
        )
    if create_log and new_payment:
        order.log_action(
            'pretix.event.order.payment.changed' if open_payment else 'pretix.event.order.payment.started',
            {
                'fee': new_fee,
                'old_fee': old_fee,
                'provider': payment_provider.identifier,
                'payment': new_payment.pk,
                'local_id': new_payment.local_id,
            }
        )

    if recreate_invoices:
        i = order.invoices.filter(is_cancellation=False).last()
        if i and order.total != oldtotal:
            generate_cancellation(i)
            generate_invoice(order)

    return old_fee, new_fee, fee, new_payment
