from datetime import timedelta, datetime
from django.db import transaction
from django.utils.timezone import now
from pretix.base.models import Order, Quota, OrderPosition
from django.utils.translation import ugettext_lazy as _
from pretix.base.services.mail import mail
from pretix.helpers.urls import build_absolute_uri


def mark_order_paid(order, provider=None, info=None, date=None, manual=None, force=False):
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
    can_be_paid, quotas_locked = order._can_be_paid(keep_locked=True)
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

    if quotas_locked:
        for quota in quotas_locked:
            quota.release()

    from pretix.base.services.mail import mail

    mail(
        order.user, _('Payment received for your order: %(code)s') % {'code': order.code},
        'pretixpresale/email/order_paid.txt',
        {
            'user': order.user,
            'order': order,
            'event': order.event,
            'url': build_absolute_uri('presale:event.order', kwargs={
                'event': order.event.slug,
                'organizer': order.event.organizer.slug,
                'order': order.code,
            }),
            'downloads': order.event.settings.get('ticket_download', as_type=bool)
        },
        order.event
    )
    return order


class OrderError(Exception):
    pass


def check_positions(event, dt, positions, quotas_locked):
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
            # Lock the quota, so no other thread is allowed to perform sales covered by this
            # quota while we're doing so.
            if quota not in quotas_locked:
                quota.lock()
                quotas_locked.add(quota)
            avail = quota.availability()
            if avail[0] != Quota.AVAILABILITY_OK:
                # This quota is sold out/currently unavailable, so do not sell this at all
                err = err or error_messages['unavailable']
                quota_ok = False
                break
        if quota_ok and not event.presale_end or now() < event.presale_end:
            cp = cp.clone()
            positions[i] = cp
            cp.expires = now() + timedelta(
                minutes=event.settings.get('reservation_time', as_type=int))
            cp.save()
        elif not quota_ok:
            cp.delete()  # Sorry!
    if err:
        raise OrderError(err)


def perform_order(event, user, payment_provider, positions):
    error_messages = {
        'busy': _('We were not able to process your request completely as the '
                  'server was too busy. Please try again.'),
    }
    dt = now()
    quotas_locked = set()

    try:
        check_positions(event, dt, positions, quotas_locked)
        order = place_order(event, user, positions, dt, payment_provider)
        mail(
            user, _('Your order: %(code)s') % {'code': order.code},
            'pretixpresale/email/order_placed.txt',
            {
                'user': user, 'order': order,
                'event': event,
                'url': build_absolute_uri('presale:event.order', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                    'order': order.code,
                }),
                'payment': payment_provider.order_pending_mail_render(order)
            },
            event
        )
        return order
    except Quota.LockTimeoutException:
        # Is raised when there are too many threads asking for quota locks and we were
        # unaible to get one
        raise OrderError(error_messages['busy'])
    finally:
        # Release the locks. This is important ;)
        for quota in quotas_locked:
            quota.release()


@transaction.atomic()
def place_order(event, user, positions, dt, payment_provider):
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
        datetime=dt,
        expires=min(expires),
        total=total,
        payment_fee=payment_fee,
        payment_provider=payment_provider.identifier,
    )
    OrderPosition.transform_cart_positions(positions, order)
    return order
