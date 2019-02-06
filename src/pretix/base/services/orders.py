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
from django.db.models import F, Max, Q, Sum
from django.db.models.functions import Greatest
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.api.models import OAuthApplication
from pretix.base.i18n import (
    LazyCurrencyNumber, LazyDate, LazyLocaleException, LazyNumber, language,
)
from pretix.base.models import (
    CartPosition, Device, Event, Item, ItemVariation, Order, OrderPayment,
    OrderPosition, Quota, User, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import (
    CachedCombinedTicket, CachedTicket, InvoiceAddress, OrderFee, OrderRefund,
    generate_position_secret, generate_secret,
)
from pretix.base.models.organizer import TeamAPIToken
from pretix.base.models.tax import TaxedPrice
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_qualified,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException
from pretix.base.services.pricing import get_price
from pretix.base.services.tasks import ProfiledTask
from pretix.base.signals import (
    allow_ticket_download, order_fee_calculation, order_placed, periodic_task,
)
from pretix.celery_app import app
from pretix.helpers.models import modelcopy
from pretix.multidomain.urlreverse import build_absolute_uri

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


@transaction.atomic
def mark_order_expired(order, user=None, auth=None):
    """
    Mark this order as expired. This sets the payment status and returns the order object.
    :param order: The order to change
    :param user: The user that performed the change
    """
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

    return order


@transaction.atomic
def approve_order(order, user=None, send_mail: bool=True, auth=None):
    """
    Mark this order as approved
    :param order: The order to change
    :param user: The user that performed the change
    """
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
            p.confirm(send_mail=False, count_waitinglist=False, user=user, auth=auth)
        except Quota.QuotaExceededException:
            raise OrderError(error_messages['unavailable'])

    invoice = order.invoices.last()  # Might be generated by plugin already
    if order.event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        if not invoice:
            invoice = generate_invoice(
                order,
                trigger_pdf=not order.event.settings.invoice_email_attachment or not order.email
            )
            # send_mail will trigger PDF generation later

    if send_mail:
        try:
            invoice_name = order.invoice_address.name
            invoice_company = order.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""

        with language(order.locale):
            if order.total == Decimal('0.00'):
                email_template = order.event.settings.mail_text_order_free
                email_subject = _('Order approved and confirmed: %(code)s') % {'code': order.code}
            else:
                email_template = order.event.settings.mail_text_order_approved
                email_subject = _('Order approved and awaiting payment: %(code)s') % {'code': order.code}

            email_context = {
                'total': LazyNumber(order.total),
                'currency': order.event.currency,
                'total_with_currency': LazyCurrencyNumber(order.total, order.event.currency),
                'date': LazyDate(order.expires),
                'event': order.event.name,
                'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }),
                'invoice_name': invoice_name,
                'invoice_company': invoice_company,
            }
            try:
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_approved', user,
                    invoices=[invoice] if invoice and order.event.settings.invoice_email_attachment else []
                )
            except SendMailException:
                logger.exception('Order approved email could not be sent')

    return order.pk


@transaction.atomic
def deny_order(order, comment='', user=None, send_mail: bool=True, auth=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
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

    if send_mail:
        try:
            invoice_name = order.invoice_address.name
            invoice_company = order.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""
        email_template = order.event.settings.mail_text_order_denied
        email_context = {
            'total': LazyNumber(order.total),
            'currency': order.event.currency,
            'total_with_currency': LazyCurrencyNumber(order.total, order.event.currency),
            'date': LazyDate(order.expires),
            'event': order.event.name,
            'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret
            }),
            'comment': comment,
            'invoice_name': invoice_name,
            'invoice_company': invoice_company,
        }
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


@transaction.atomic
def _cancel_order(order, user=None, send_mail: bool=True, api_token=None, device=None, oauth_application=None,
                  cancellation_fee=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
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
        email_context = {
            'event': order.event.name,
            'code': order.code,
            'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret
            })
        }
        with language(order.locale):
            email_subject = _('Order canceled: %(code)s') % {'code': order.code}
            try:
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_canceled', user
                )
            except SendMailException:
                logger.exception('Order canceled email could not be sent')

    return order.pk


class OrderError(LazyLocaleException):
    pass


def _check_date(event: Event, now_dt: datetime):
    if event.presale_start and now_dt < event.presale_start:
        raise OrderError(error_messages['not_started'])
    if event.presale_has_ended:
        raise OrderError(error_messages['ended'])


def _check_positions(event: Event, now_dt: datetime, positions: List[CartPosition], address: InvoiceAddress=None):
    err = None
    errargs = None
    _check_date(event, now_dt)

    products_seen = Counter()
    for i, cp in enumerate(positions):
        if not cp.item.is_available() or (cp.variation and not cp.variation.active):
            err = err or error_messages['unavailable']
            cp.delete()
            continue
        quotas = list(cp.quotas)

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

        if cp.subevent and cp.subevent.presale_start and now_dt < cp.subevent.presale_start:
            err = err or error_messages['some_subevent_not_started']
            cp.delete()
            break

        if cp.subevent and cp.subevent.presale_has_ended:
            err = err or error_messages['some_subevent_ended']
            cp.delete()
            break

        if cp.item.require_voucher and cp.voucher is None:
            cp.delete()
            err = err or error_messages['voucher_required']
            break

        if cp.item.hide_without_voucher and (cp.voucher is None or cp.voucher.item is None
                                             or cp.voucher.item.pk != cp.item.pk):
            cp.delete()
            err = error_messages['voucher_required']
            break

        if cp.expires >= now_dt and not cp.voucher:
            # Other checks are not necessary
            continue

        price = get_price(cp.item, cp.variation, cp.voucher, cp.price, cp.subevent, custom_price_is_net=False,
                          addon_to=cp.addon_to, invoice_address=address)

        if price is False or len(quotas) == 0:
            err = err or error_messages['unavailable']
            cp.delete()
            continue

        if cp.voucher:
            if cp.voucher.valid_until and cp.voucher.valid_until < now_dt:
                err = err or error_messages['voucher_expired']
                cp.delete()
                continue

        if price.gross != cp.price and not (cp.item.free_price and cp.price > price.gross):
            positions[i] = cp
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
            positions[i] = cp
            cp.expires = now_dt + timedelta(
                minutes=event.settings.get('reservation_time', as_type=int))
            cp.save()
        else:
            cp.delete()  # Sorry!
    if err:
        raise OrderError(err, errargs)


def _get_fees(positions: List[CartPosition], payment_provider: BasePaymentProvider, address: InvoiceAddress,
              meta_info: dict, event: Event):
    fees = []
    total = sum([c.price for c in positions])
    if payment_provider:
        payment_fee = payment_provider.calculate_fee(total)
    else:
        payment_fee = 0
    pf = None
    if payment_fee:
        pf = OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=payment_fee,
                      internal_type=payment_provider.identifier)
        fees.append(pf)

    for recv, resp in order_fee_calculation.send(sender=event, invoice_address=address, total=total,
                                                 meta_info=meta_info, positions=positions):
        fees += resp
    return fees, pf


def _create_order(event: Event, email: str, positions: List[CartPosition], now_dt: datetime,
                  payment_provider: BasePaymentProvider, locale: str=None, address: InvoiceAddress=None,
                  meta_info: dict=None, sales_channel: str='web'):
    fees, pf = _get_fees(positions, payment_provider, address, meta_info, event)
    total = sum([c.price for c in positions]) + sum([c.value for c in fees])

    with transaction.atomic():
        order = Order(
            status=Order.STATUS_PENDING,
            event=event,
            email=email,
            datetime=now_dt,
            locale=locale,
            total=total,
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
            order.payments.create(
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
    return order


def _perform_order(event: str, payment_provider: str, position_ids: List[str],
                   email: str, locale: str, address: int, meta_info: dict=None, sales_channel: str='web'):

    event = Event.objects.get(id=event)
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
            addr = InvoiceAddress.objects.get(pk=address)
        except InvoiceAddress.DoesNotExist:
            pass

    with event.lock() as now_dt:
        positions = list(CartPosition.objects.filter(
            id__in=position_ids).select_related('item', 'variation', 'subevent'))
        if len(positions) == 0:
            raise OrderError(error_messages['empty'])
        if len(position_ids) != len(positions):
            raise OrderError(error_messages['internal'])
        _check_positions(event, now_dt, positions, address=addr)
        order = _create_order(event, email, positions, now_dt, pprov,
                              locale=locale, address=addr, meta_info=meta_info, sales_channel=sales_channel)

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
        elif payment_provider == 'free':
            email_template = event.settings.mail_text_order_free
            log_entry = 'pretix.event.order.email.order_free'
        else:
            email_template = event.settings.mail_text_order_placed
            log_entry = 'pretix.event.order.email.order_placed'

        try:
            invoice_name = order.invoice_address.name
            invoice_company = order.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""

        if pprov:
            payment_info = str(pprov.order_pending_mail_render(order))
        else:
            payment_info = None

        email_context = {
            'total': LazyNumber(order.total),
            'currency': event.currency,
            'total_with_currency': LazyCurrencyNumber(order.total, event.currency),
            'date': LazyDate(order.expires),
            'event': event.name,
            'url': build_absolute_uri(event, 'presale:event.order', kwargs={
                'order': order.code,
                'secret': order.secret
            }),
            'payment_info': payment_info,
            'invoice_name': invoice_name,
            'invoice_company': invoice_company,
        }
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

    return order.id


@receiver(signal=periodic_task)
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
def send_expiry_warnings(sender, **kwargs):
    eventcache = {}
    today = now().replace(hour=0, minute=0, second=0)

    for o in Order.objects.filter(
        expires__gte=today, expiry_reminder_sent=False, status=Order.STATUS_PENDING, datetime__lte=now() - timedelta(hours=2)
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
            tz = pytz.timezone(eventsettings.get('timezone', settings.TIME_ZONE))
            if days and (o.expires - today).days <= days:
                with language(o.locale):
                    o.expiry_reminder_sent = True
                    o.save(update_fields=['expiry_reminder_sent'])
                    try:
                        invoice_name = o.invoice_address.name
                        invoice_company = o.invoice_address.company
                    except InvoiceAddress.DoesNotExist:
                        invoice_name = ""
                        invoice_company = ""
                    email_template = eventsettings.mail_text_order_expire_warning
                    email_context = {
                        'event': o.event.name,
                        'url': build_absolute_uri(o.event, 'presale:event.order', kwargs={
                            'order': o.code,
                            'secret': o.secret
                        }),
                        'expire_date': date_format(o.expires.astimezone(tz), 'SHORT_DATE_FORMAT'),
                        'invoice_name': invoice_name,
                        'invoice_company': invoice_company,
                    }
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
                    email_context = {
                        'event': o.event.name,
                        'url': build_absolute_uri(o.event, 'presale:event.order', kwargs={
                            'order': o.code,
                            'secret': o.secret
                        }),
                    }
                    email_subject = _('Your ticket is ready for download: %(code)s') % {'code': o.code}
                    try:
                        o.send_mail(
                            email_subject, email_template, email_context,
                            'pretix.event.order.email.download_reminder_sent',
                            attach_tickets=True
                        )
                    except SendMailException:
                        logger.exception('Reminder email could not be sent')


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
    }
    ItemOperation = namedtuple('ItemOperation', ('position', 'item', 'variation', 'price'))
    SubeventOperation = namedtuple('SubeventOperation', ('position', 'subevent', 'price'))
    PriceOperation = namedtuple('PriceOperation', ('position', 'price'))
    CancelOperation = namedtuple('CancelOperation', ('position',))
    AddOperation = namedtuple('AddOperation', ('item', 'variation', 'price', 'addon_to', 'subevent'))
    SplitOperation = namedtuple('SplitOperation', ('position',))
    RegenerateSecretOperation = namedtuple('RegenerateSecretOperation', ('position',))

    def __init__(self, order: Order, user=None, auth=None, notify=True):
        self.order = order
        self.user = user
        self.auth = auth
        self.split_order = None
        self._committed = False
        self._totaldiff = 0
        self._quotadiff = Counter()
        self._operations = []
        self.notify = notify
        self._invoice_dirty = False

    def change_item(self, position: OrderPosition, item: Item, variation: Optional[ItemVariation]):
        if (not variation and item.has_variations) or (variation and variation.item_id != item.pk):
            raise OrderError(self.error_messages['product_without_variation'])

        price = get_price(item, variation, voucher=position.voucher, subevent=position.subevent,
                          invoice_address=self._invoice_address)

        if price is None:  # NOQA
            raise OrderError(self.error_messages['product_invalid'])

        new_quotas = (variation.quotas.filter(subevent=position.subevent)
                      if variation else item.quotas.filter(subevent=position.subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00') or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._totaldiff += price.gross - position.price
        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.ItemOperation(position, item, variation, price))

    def change_subevent(self, position: OrderPosition, subevent: SubEvent):
        price = get_price(position.item, position.variation, voucher=position.voucher, subevent=subevent,
                          invoice_address=self._invoice_address)

        if price is None:  # NOQA
            raise OrderError(self.error_messages['product_invalid'])

        new_quotas = (position.variation.quotas.filter(subevent=subevent)
                      if position.variation else position.item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00') or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._totaldiff += price.gross - position.price
        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.SubeventOperation(position, subevent, price))

    def regenerate_secret(self, position: OrderPosition):
        self._operations.append(self.RegenerateSecretOperation(position))

    def change_price(self, position: OrderPosition, price: Decimal):
        price = position.item.tax(price)

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

        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

    def add_position(self, item: Item, variation: ItemVariation, price: Decimal, addon_to: Order = None,
                     subevent: SubEvent = None):
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

        new_quotas = (variation.quotas.filter(subevent=subevent)
                      if variation else item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00'):
            self._invoice_dirty = True

        self._totaldiff += price.gross
        self._quotadiff.update(new_quotas)
        self._operations.append(self.AddOperation(item, variation, price, addon_to, subevent))

    def split(self, position: OrderPosition):
        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._operations.append(self.SplitOperation(position))

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
            if self.order.pending_sum <= Decimal('0.00'):
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
        if self.order.total == 0 and (self._totaldiff < 0 or (self.split_order and self.split_order.total > 0)):
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

        if self.split_order and self.split_order.total == 0:
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
        nextposid = self.order.positions.aggregate(m=Max('positionid'))['m'] + 1
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
                    'new_price': op.price.gross
                })
                op.position.item = op.item
                op.position.variation = op.variation
                op.position.price = op.price.gross
                op.position.tax_rate = op.price.rate
                op.position.tax_value = op.price.tax
                op.position.tax_rule = op.item.tax_rule
                op.position.save()
            elif isinstance(op, self.SubeventOperation):
                self.order.log_action('pretix.event.order.changed.subevent', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                    'old_subevent': op.position.subevent.pk,
                    'new_subevent': op.subevent.pk,
                    'old_price': op.position.price,
                    'new_price': op.price.gross
                })
                op.position.subevent = op.subevent
                op.position.price = op.price.gross
                op.position.tax_rate = op.price.rate
                op.position.tax_value = op.price.tax
                op.position.tax_rule = op.position.item.tax_rule
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
                op.position.tax_rate = op.price.rate
                op.position.tax_value = op.price.tax
                op.position.tax_rule = op.position.item.tax_rule
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
                    positionid=nextposid, subevent=op.subevent
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
                })
            elif isinstance(op, self.SplitOperation):
                split_positions.append(op.position)
            elif isinstance(op, self.RegenerateSecretOperation):
                op.position.secret = generate_position_secret()
                op.position.save()
                CachedTicket.objects.filter(order_position__order=self.order).delete()
                CachedCombinedTicket.objects.filter(order=self.order).delete()
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

        for fee in self.order.fees.exclude(fee_type=OrderFee.FEE_TYPE_PAYMENT):
            new_fee = modelcopy(fee)
            new_fee.pk = None
            new_fee.order = split_order
            split_order.total += new_fee.value
            new_fee.save()

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
        if i and self._invoice_dirty:
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

    def _notify_user(self, order):
        with language(order.locale):
            try:
                invoice_name = order.invoice_address.name
                invoice_company = order.invoice_address.company
            except InvoiceAddress.DoesNotExist:
                invoice_name = ""
                invoice_company = ""
            email_template = order.event.settings.mail_text_order_changed
            email_context = {
                'event': order.event.name,
                'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }),
                'invoice_name': invoice_name,
                'invoice_company': invoice_company,
            }
            email_subject = _('Your order has been changed: %(code)s') % {'code': order.code}
            try:
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_changed', self.user, auth=self.auth
                )
            except SendMailException:
                logger.exception('Order changed email could not be sent')

    def commit(self):
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
                self._check_quotas()
                self._check_complete_cancel()
                self._perform_operations()
            self._recalculate_total_and_payment_fee()
            self._reissue_invoice()
            self._clear_tickets_cache()
            self.order.touch()
        self._check_paid_price_change()
        self._check_paid_to_free()

        if self.notify:
            self._notify_user(self.order)
            if self.split_order:
                self._notify_user(self.split_order)

    def _clear_tickets_cache(self):
        CachedTicket.objects.filter(order_position__order=self.order).delete()
        CachedCombinedTicket.objects.filter(order=self.order).delete()
        if self.split_order:
            CachedTicket.objects.filter(order_position__order=self.split_order).delete()
            CachedCombinedTicket.objects.filter(order=self.split_order).delete()

    def _get_payment_provider(self):
        lp = self.order.payments.last()
        if not lp:
            return None
        pprov = lp.payment_provider
        if not pprov:
            return None
        return pprov


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def perform_order(self, event: str, payment_provider: str, positions: List[str],
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
                else:
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
