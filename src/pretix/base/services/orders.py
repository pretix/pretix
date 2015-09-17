from datetime import datetime, timedelta

from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import (
    Event, EventLock, Order, OrderPosition, Quota, User,
)
from pretix.base.services.mail import mail
from pretix.base.signals import order_paid, order_placed
from pretix.helpers.urls import build_absolute_uri


def mark_order_paid(order: Order, provider: str=None, info: str=None, date: datetime=None, manual: bool=None,
                    force: bool=False):
    """
    Marks an order as paid. This clones the order object, sets the payment provider,
    info and date and returns the cloned order object.

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
    :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
    """
    with order.event.lock():
        can_be_paid = order._can_be_paid()
        if not force and can_be_paid is not True:
            raise Quota.QuotaExceededException(can_be_paid)
        order = order.clone()
        order.payment_provider = provider or order.payment_provider
        order.payment_info = info or order.payment_info
        order.payment_date = date or now()
        if manual is not None:
            order.payment_manual = manual
        order.status = Order.STATUS_PAID
        order.save()
        order_paid.send(order.event, order=order)

    from pretix.base.services.mail import mail

    mail(
        order.email, _('Payment received for your order: %(code)s') % {'code': order.code},
        'pretixpresale/email/order_paid.txt',
        {
            'order': order,
            'event': order.event,
            'url': build_absolute_uri('presale:event.order', kwargs={
                'event': order.event.slug,
                'organizer': order.event.organizer.slug,
                'order': order.code,
            }) + '?order_secret=' + order.secret,
            'downloads': order.event.settings.get('ticket_download', as_type=bool)
        },
        order.event, locale=order.locale
    )
    return order


class OrderError(Exception):
    pass


def check_positions(event: Event, dt: datetime, positions: list):
    error_messages = {
        'unavailable': _('Some of the products you selected were no longer available. '
                         'Please see below for details.'),
        'in_part': _('Some of the products you selected were no longer available in '
                     'the quantity you selected. Please see below for details.'),
        'price_changed': _('The price of some of the items in your cart has changed in the '
                           'meantime. Please see below for details.'),
        'max_items': _("You cannot select more than %s items per order"),
    }
    err = None

    for i, cp in enumerate(positions):
        if not cp.item.active:
            err = err or error_messages['unavailable']
            continue
        quotas = list(cp.item.quotas.all()) if cp.variation is None else list(cp.variation.quotas.all())
        if cp.expires >= dt:
            # Other checks are not necessary
            continue
        price = cp.item.check_restrictions() if cp.variation is None else cp.variation.check_restrictions()
        if price is False or len(quotas) == 0:
            err = err or error_messages['unavailable']
            continue
        if price != cp.price:
            cp = cp.clone()
            positions[i] = cp
            cp.price = price
            cp.save()
            err = err or error_messages['price_changed']
            continue
        quota_ok = True
        for quota in quotas:
            avail = quota.availability()
            if avail[0] != Quota.AVAILABILITY_OK:
                # This quota is sold out/currently unavailable, so do not sell this at all
                err = err or error_messages['unavailable']
                quota_ok = False
                break
        if quota_ok and (not event.presale_end or now() < event.presale_end):
            cp = cp.clone()
            positions[i] = cp
            cp.expires = now() + timedelta(
                minutes=event.settings.get('reservation_time', as_type=int))
            cp.save()
        elif not quota_ok:
            cp.delete()  # Sorry!
    if err:
        raise OrderError(err)


def perform_order(event: Event, payment_provider: str, positions: list, user: User=None, email: str=None,
                  locale: str=None):
    error_messages = {
        'busy': _('We were not able to process your request completely as the '
                  'server was too busy. Please try again.'),
    }
    dt = now()

    try:
        with event.lock():
            check_positions(event, dt, positions)
            order = place_order(event, user, email if user is None else None, positions, dt, payment_provider,
                                locale=locale)
            mail(
                order.email, _('Your order: %(code)s') % {'code': order.code},
                'pretixpresale/email/order_placed.txt',
                {
                    'order': order,
                    'event': event,
                    'url': build_absolute_uri('presale:event.order', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order.code,
                    }) + '?order_secret=' + order.secret,
                    'payment': payment_provider.order_pending_mail_render(order)
                },
                event, locale=order.locale
            )
            return order
    except EventLock.LockTimeoutException:
        # Is raised when there are too many threads asking for event locks and we were
        # unable to get one
        raise OrderError(error_messages['busy'])


@transaction.atomic()
def place_order(event: Event, user: User, email: str, positions: list, dt: datetime, payment_provider: str,
                locale: str=None):
    total = sum([c.price for c in positions])
    payment_fee = payment_provider.calculate_fee(total)
    total += payment_fee
    expires = [dt + timedelta(days=event.settings.get('payment_term_days', as_type=int))]
    if event.settings.get('payment_term_last'):
        expires.append(event.settings.get('payment_term_last', as_type=datetime))
    order = Order.objects.create(
        status=Order.STATUS_PENDING,
        event=event,
        user=user,
        guest_email=email,
        datetime=dt,
        expires=min(expires),
        locale=locale,
        total=total,
        payment_fee=payment_fee,
        payment_provider=payment_provider.identifier,
    )
    OrderPosition.transform_cart_positions(positions, order)
    order_placed.send(event, order=order)
    return order
