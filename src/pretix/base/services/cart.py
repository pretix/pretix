from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from typing import List, Optional, Tuple

from pretix.base.i18n import LazyLocaleException
from pretix.base.models import (
    CartPosition, Event, EventLock, Item, ItemVariation, Quota, Voucher,
)


class CartError(LazyLocaleException):
    pass


error_messages = {
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'empty': _('You did not select any products.'),
    'not_for_sale': _('You selected a product which is not available for sale.'),
    'unavailable': _('Some of the products you selected were no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected were no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'max_items': _("You cannot select more than %s items per order"),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period has ended.'),
    'voucher_invalid': _('This voucher code is not known in our database.'),
    'voucher_redeemed': _('This voucher code has already been used an can only be used once.'),
    'voucher_expired': _('This voucher is expired'),
}


def _extend_existing(event: Event, cart_id: str, expiry: datetime) -> None:
    # Extend this user's cart session to 30 minutes from now to ensure all items in the
    # cart expire at the same time
    # We can extend the reservation of items which are not yet expired without risk
    CartPosition.objects.filter(
        Q(cart_id=cart_id) & Q(event=event) & Q(expires__gt=now())
    ).update(expires=expiry)


def _re_add_expired_positions(items: List[CartPosition], event: Event, cart_id: str) -> List[CartPosition]:
    positions = set()
    # For items that are already expired, we have to delete and re-add them, as they might
    # be no longer available or prices might have changed. Sorry!
    expired = CartPosition.objects.filter(
        Q(cart_id=cart_id) & Q(event=event) & Q(expires__lte=now())
    )
    for cp in expired:
        items.insert(0, (cp.item_id, cp.variation_id, 1, cp.price, cp))
        positions.add(cp)
    return positions


def _delete_expired(expired: List[CartPosition]) -> None:
    for cp in expired:
        if cp.expires <= now():
            cp.delete()


def _check_date(event: Event) -> None:
    if event.presale_start and now() < event.presale_start:
        raise CartError(error_messages['not_started'])
    if event.presale_end and now() > event.presale_end:
        raise CartError(error_messages['ended'])


def _add_new_items(event: Event, items: List[Tuple[int, Optional[int], int, Optional[str]]],
                   cart_id: str, expiry: datetime) -> Optional[str]:
    err = None

    # Fetch items from the database
    items_query = Item.objects.filter(event=event, id__in=[i[0] for i in items]).prefetch_related(
        "quotas")
    items_cache = {i.id: i for i in items_query}
    variations_query = ItemVariation.objects.filter(
        item__event=event,
        id__in=[i[1] for i in items if i[1] is not None]
    ).select_related("item", "item__event").prefetch_related("quotas")
    variations_cache = {v.id: v for v in variations_query}

    for i in items:
        # Check whether the specified items are part of what we just fetched from the database
        # If they are not, the user supplied item IDs which either do not exist or belong to
        # a different event
        if i[0] not in items_cache or (i[1] is not None and i[1] not in variations_cache):
            err = err or error_messages['not_for_sale']
            continue

        item = items_cache[i[0]]
        variation = variations_cache[i[1]] if i[1] is not None else None

        # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
        quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())

        if len(quotas) == 0 or not item.is_available():
            err = err or error_messages['unavailable']
            continue

        # Check that all quotas allow us to buy i[2] instances of the object
        quota_ok = i[2]
        for quota in quotas:
            avail = quota.availability()
            if avail[1] is not None and avail[1] < i[2]:
                # This quota is not available or less than i[2] items are left, so we have to
                # reduce the number of bought items
                if avail[0] != Quota.AVAILABILITY_OK:
                    err = err or error_messages['unavailable']
                else:
                    err = err or error_messages['in_part']
                quota_ok = min(quota_ok, avail[1])

        price = item.default_price if variation is None else (
            variation.default_price if variation.default_price is not None else item.default_price)
        if item.free_price and len(i) > 3 and i[3]:
            custom_price = i[3]
            if not isinstance(custom_price, Decimal):
                custom_price = Decimal(custom_price.replace(",", "."))
            price = max(custom_price, price)

        # Create a CartPosition for as much items as we can
        for k in range(quota_ok):
            if len(i) > 4 and i[2] == 1:
                # Recreating
                cp = i[4]
                cp.expires = expiry
                cp.price = price
                cp.save()
            else:
                CartPosition.objects.create(
                    event=event, item=item, variation=variation,
                    price=price,
                    expires=expiry,
                    cart_id=cart_id
                )
    return err


def _add_voucher(event: Event, voucher: str, expiry: datetime, cart_id: str):
    try:
        v = Voucher.objects.get(code=voucher, event=event)
        if v.redeemed:
            raise CartError(error_messages['voucher_redeemed'])
        if v.valid_until is not None and v.valid_until < now():
            raise CartError(error_messages['voucher_expired'])

        quotas = list(v.item.quotas.all())
        if len(quotas) == 0 or not v.item.is_available():
            raise CartError(error_messages['unavailable'])

        if not v.allow_ignore_quota and not v.block_quota:
            for quota in quotas:
                avail = quota.availability()
                if avail[1] is not None and avail[1] < 1:
                    raise CartError(error_messages['unavailable'])

        CartPosition.objects.create(
            event=event, item=v.item, variation=v.variation,
            price=v.price if v.price is not None else v.item.default_price,
            expires=expiry, cart_id=cart_id, voucher=v
        )
    except Voucher.DoesNotExist:
        raise CartError(error_messages['voucher_invalid'])


def _add_items_to_cart(event: Event, items: List[Tuple[int, Optional[int], int, Optional[str]]], cart_id: str=None,
                       voucher: str=None) -> None:
    with event.lock():
        _check_date(event)
        existing = CartPosition.objects.filter(Q(cart_id=cart_id) & Q(event=event)).count()
        if sum(i[2] for i in items) + existing > int(event.settings.max_items_per_order):
            # TODO: i18n plurals
            raise CartError(error_messages['max_items'], (event.settings.max_items_per_order,))

        expiry = now() + timedelta(minutes=event.settings.get('reservation_time', as_type=int))
        _extend_existing(event, cart_id, expiry)

        expired = _re_add_expired_positions(items, event, cart_id)
        if items:
            err = _add_new_items(event, items, cart_id, expiry)
            _delete_expired(expired)
            if err:
                raise CartError(err)
        elif not voucher:
            raise CartError(error_messages['empty'])

        if voucher:
            _add_voucher(event, voucher, expiry, cart_id)


def add_items_to_cart(event: int, items: List[Tuple[int, Optional[int], int, Optional[str]]], cart_id: str=None,
                      voucher: str=None) -> None:
    """
    Adds a list of items to a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number, custom_price)
    :param session: Session ID of a guest
    :param coupon: A coupon that should also be reeemed
    :raises CartError: On any error that occured
    """
    event = Event.objects.get(id=event)
    try:
        _add_items_to_cart(event, items, cart_id, voucher)
    except EventLock.LockTimeoutException:
        raise CartError(error_messages['busy'])


def _remove_items_from_cart(event: int, items: List[Tuple[int, Optional[int], int, Optional[str]]],
                            cart_id: str) -> None:
    with event.lock():
        for item, variation, cnt, price in items:
            cw = Q(cart_id=cart_id) & Q(item_id=item) & Q(event=event)
            if variation:
                cw &= Q(variation_id=variation)
            else:
                cw &= Q(variation__isnull=True)
            # Prefer to delete positions that have the same price as the one the user clicked on, after thet
            # prefer the most expensive ones.
            if price:
                correctprice = CartPosition.objects.filter(cw).filter(price=Decimal(price.replace(",", ".")))[:cnt]
                for cp in correctprice:
                    cp.delete()
                cnt -= len(correctprice)
            if cnt > 0:
                for cp in CartPosition.objects.filter(cw).order_by("-price")[:cnt]:
                    cp.delete()


def remove_items_from_cart(event: int, items: List[Tuple[int, Optional[int], int, Optional[str]]],
                           cart_id: str=None) -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number)
    :param session: Session ID of a guest
    """
    event = Event.objects.get(id=event)
    try:
        _remove_items_from_cart(event, items, cart_id)
    except EventLock.LockTimeoutException:
        raise CartError(error_messages['busy'])


if settings.HAS_CELERY:
    from pretix.celery import app

    @app.task(bind=True, max_retries=5, default_retry_delay=1)
    def add_items_to_cart_task(self, event: int, items: List[Tuple[int, Optional[int], int, Optional[str]]],
                               cart_id: str, voucher: str=None):
        event = Event.objects.get(id=event)
        try:
            try:
                _add_items_to_cart(event, items, cart_id, voucher)
            except EventLock.LockTimeoutException:
                self.retry(exc=CartError(error_messages['busy']))
        except CartError as e:
            return e

    @app.task(bind=True, max_retries=5, default_retry_delay=1)
    def remove_items_from_cart_task(self, event: int, items: List[Tuple[int, Optional[int], int]],
                                    cart_id: str):
        event = Event.objects.get(id=event)
        try:
            try:
                _remove_items_from_cart(event, items, cart_id)
            except EventLock.LockTimeoutException:
                self.retry(exc=CartError(error_messages['busy']))
        except CartError as e:
            return e

    add_items_to_cart.task = add_items_to_cart_task
    remove_items_from_cart.task = remove_items_from_cart_task
