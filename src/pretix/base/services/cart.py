from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from celery.exceptions import MaxRetriesExceededError
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.i18n import LazyLocaleException
from pretix.base.models import (
    CartPosition, Event, Item, ItemVariation, Quota, Voucher,
)
from pretix.base.services.async import ProfiledTask
from pretix.base.services.locking import LockTimeoutException
from pretix.celery import app


class CartError(LazyLocaleException):
    pass


error_messages = {
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'empty': _('You did not select any products.'),
    'not_for_sale': _('You selected a product which is not available for sale.'),
    'unavailable': _('Some of the products you selected are no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected are no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'max_items': _("You cannot select more than %s items per order."),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period has ended.'),
    'price_too_high': _('The entered price is to high.'),
    'voucher_invalid': _('This voucher code is not known in our database.'),
    'voucher_redeemed': _('This voucher code has already been used the maximum number of times allowed.'),
    'voucher_redeemed_partial': _('This voucher code can only be redeemed %d more times.'),
    'voucher_double': _('You already used this voucher code. Remove the associated line from your '
                        'cart if you want to use it for a different product.'),
    'voucher_expired': _('This voucher is expired.'),
    'voucher_invalid_item': _('This voucher is not valid for this product.'),
    'voucher_required': _('You need a valid voucher code to order this product.'),
}


def _extend_existing(event: Event, cart_id: str, expiry: datetime, now_dt: datetime) -> None:
    # Extend this user's cart session to 30 minutes from now to ensure all items in the
    # cart expire at the same time
    # We can extend the reservation of items which are not yet expired without risk
    CartPosition.objects.filter(
        Q(cart_id=cart_id) & Q(event=event) & Q(expires__gt=now_dt)
    ).update(expires=expiry)


def _re_add_expired_positions(items: List[dict], event: Event, cart_id: str, now_dt: datetime) -> List[CartPosition]:
    positions = set()
    # For items that are already expired, we have to delete and re-add them, as they might
    # be no longer available or prices might have changed. Sorry!
    expired = CartPosition.objects.filter(
        Q(cart_id=cart_id) & Q(event=event) & Q(expires__lte=now_dt)
    )
    for cp in expired:
        items.insert(0, {
            'item': cp.item_id,
            'variation': cp.variation_id,
            'count': 1,
            'price': cp.price,
            '_cp': cp,
            'voucher': cp.voucher.code if cp.voucher else None
        })
        positions.add(cp)
    return positions


def _delete_expired(expired: List[CartPosition], now_dt: datetime) -> None:
    for cp in expired:
        if cp.expires <= now_dt:  # Has not been extended
            cp.delete()


def _check_date(event: Event, now_dt: datetime) -> None:
    if event.presale_start and now_dt < event.presale_start:
        raise CartError(error_messages['not_started'])
    if event.presale_end and now_dt > event.presale_end:
        raise CartError(error_messages['ended'])


def _parse_items_and_check_constraints(event: Event, items: List[dict], cart_id: str,
                                       now_dt: datetime) -> Counter:
    """
    This method does three things:

    * Extend the item list with the database objects for the item, variation, etc.

    * Check all constraints that are placed on the items, vouchers etc. to be valid and calculates the correct prices

    * Return a counter object that contains the quota changes that are required to perform the operation
    """
    err = None

    # Fetch items from the database
    items_query = Item.objects.filter(event=event, id__in=[i['item'] for i in items]).prefetch_related(
        "quotas")
    items_cache = {i.id: i for i in items_query}
    variations_query = ItemVariation.objects.filter(
        item__event=event,
        id__in=[i['variation'] for i in items if i['variation'] is not None]
    ).select_related("item", "item__event").prefetch_related("quotas")
    variations_cache = {v.id: v for v in variations_query}

    quotadiff = Counter()

    for i in items:
        # Check whether the specified items are part of what we just fetched from the database
        # If they are not, the user supplied item IDs which either do not exist or belong to
        # a different event
        if i['item'] not in items_cache or (i['variation'] is not None and i['variation'] not in variations_cache):
            err = err or error_messages['not_for_sale']
            continue

        item = items_cache[i['item']]
        variation = variations_cache[i['variation']] if i['variation'] is not None else None

        # Check whether a voucher has been provided
        voucher = None
        if i.get('voucher'):
            try:
                voucher = Voucher.objects.get(code=i.get('voucher').strip(), event=event)
                if voucher.redeemed >= voucher.max_usages:
                    return error_messages['voucher_redeemed']
                if voucher.valid_until is not None and voucher.valid_until < now_dt:
                    raise CartError(error_messages['voucher_expired'])
                if not voucher.applies_to(item, variation):
                    return error_messages['voucher_invalid_item']

                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=voucher) & Q(event=event) &
                    (Q(expires__gte=now_dt) | Q(cart_id=cart_id))
                )
                if 'cp' in i:
                    redeemed_in_carts = redeemed_in_carts.exclude(pk=i['cp'].pk)
                v_avail = voucher.max_usages - voucher.redeemed - redeemed_in_carts.count()

                if v_avail < 1:
                    return error_messages['voucher_redeemed']
                if i['count'] > v_avail:
                    return error_messages['voucher_redeemed_partial'] % v_avail
            except Voucher.DoesNotExist:
                raise CartError(error_messages['voucher_invalid'])

        # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
        quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())

        if voucher and voucher.quota and voucher.quota.pk not in [q.pk for q in quotas]:
            raise CartError(error_messages['voucher_invalid_item'])

        if item.require_voucher and voucher is None:
            raise CartError(error_messages['voucher_required'])

        if item.hide_without_voucher and (voucher is None or voucher.item is None or voucher.item.pk != item.pk):
            raise CartError(error_messages['voucher_required'])

        if len(quotas) == 0 or not item.is_available() or (variation and not variation.active):
            err = err or error_messages['unavailable']
            continue

        if voucher and voucher.price is not None:
            price = voucher.price
        else:
            price = item.default_price if variation is None else (
                variation.default_price if variation.default_price is not None else item.default_price)

        if item.free_price and 'price' in i and i['price'] is not None and i['price'] != "":
            custom_price = i['price']
            if not isinstance(custom_price, Decimal):
                custom_price = Decimal(custom_price.replace(",", "."))
            if custom_price > 100000000:
                raise CartError(error_messages['price_too_high'])
            price = max(custom_price, price)

        # Check that all quotas allow us to buy i['count'] instances of the object
        if not voucher or (not voucher.allow_ignore_quota and not voucher.block_quota):
            for quota in quotas:
                quotadiff[quota] += i['count']
            i['_quotas'] = quotas
        else:
            i['_quotas'] = []

        i['_price'] = price
        i['_item'] = item
        i['_variation'] = variation
        i['_voucher'] = voucher

    if err:
        raise CartError(err)

    return quotadiff


def _check_quota_and_create_positions(event: Event, items: List[dict], cart_id: str,
                                      expiry: datetime, quotadiff: Counter):
    """
    This method takes the modified items and the quotadiff from _parse_items_and_check_constraints
    and then

    * checks that the given quotas are available

    * creates as many cart positions as possible
    """
    err = None
    quotas_ok = {}
    cartpositions = []

    with event.lock():

        for quota, count in quotadiff.items():
            avail = quota.availability()
            if avail[1] is not None and avail[1] < count:
                # This quota is not available or less than i['count'] items are left, so we have to
                # reduce the number of bought items
                if avail[0] != Quota.AVAILABILITY_OK:
                    err = err or error_messages['unavailable']
                else:
                    err = err or error_messages['in_part']
                quotas_ok[quota] = min(count, avail[1])
            else:
                quotas_ok[quota] = count

        for i in items:
            # Create a CartPosition for as much items as we can
            requested_count = i['count']
            available_count = requested_count
            if i['_quotas']:
                available_count = min(requested_count, min(quotas_ok[q] for q in i['_quotas']))

            for q in i['_quotas']:
                quotas_ok[q] -= available_count

            for k in range(available_count):
                if '_cp' in i and i['count'] == 1:
                    # Recreating an existing position
                    cp = i['_cp']
                    cp.expires = expiry
                    cp.price = i['_price']
                    cp.save()
                else:
                    cartpositions.append(CartPosition(
                        event=event, item=i['_item'], variation=i['_variation'],
                        price=i['_price'],
                        expires=expiry,
                        cart_id=cart_id, voucher=i['_voucher']
                    ))

        CartPosition.objects.bulk_create(cartpositions)

    if err:
        raise CartError(err)


def _add_items_to_cart(event: Event, items: List[dict], cart_id: str=None) -> None:
    now_dt = now()
    _check_date(event, now_dt)

    existing = CartPosition.objects.filter(Q(cart_id=cart_id) & Q(event=event)).count()
    if sum(i['count'] for i in items) + existing > int(event.settings.max_items_per_order):
        # TODO: i18n plurals
        raise CartError(error_messages['max_items'], (event.settings.max_items_per_order,))

    expiry = now_dt + timedelta(minutes=event.settings.get('reservation_time', as_type=int))
    _extend_existing(event, cart_id, expiry, now_dt)

    expired = _re_add_expired_positions(items, event, cart_id, now_dt)

    try:
        if items:
            quotadiff = _parse_items_and_check_constraints(event, items, cart_id, now_dt)
            _check_quota_and_create_positions(event, items, cart_id, expiry, quotadiff)
    except CartError as e:
        _delete_expired(expired, now_dt)
        raise e
    else:
        _delete_expired(expired, now_dt)


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1)
def add_items_to_cart(self, event: int, items: List[dict], cart_id: str=None) -> None:
    """
    Adds a list of items to a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number, custom_price, voucher)
    :param session: Session ID of a guest
    :param coupon: A coupon that should also be reeemed
    :raises CartError: On any error that occured
    """
    event = Event.objects.get(id=event)
    try:
        try:
            _add_items_to_cart(event, items, cart_id)
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise CartError(error_messages['busy'])


def _remove_items_from_cart(event: Event, items: List[dict], cart_id: str) -> None:
    with event.lock():
        for i in items:
            cw = Q(cart_id=cart_id) & Q(item_id=i['item']) & Q(event=event)
            if i['variation']:
                cw &= Q(variation_id=i['variation'])
            else:
                cw &= Q(variation__isnull=True)
            # Prefer to delete positions that have the same price as the one the user clicked on, after thet
            # prefer the most expensive ones.
            cnt = i['count']
            if i['price']:
                correctprice = CartPosition.objects.filter(cw).filter(price=Decimal(i['price'].replace(",", ".")))[:cnt]
                for cp in correctprice:
                    cp.delete()
                cnt -= len(correctprice)
            if cnt > 0:
                for cp in CartPosition.objects.filter(cw).order_by("-price")[:cnt]:
                    cp.delete()


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1)
def remove_items_from_cart(self, event: int, items: List[dict], cart_id: str=None) -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param items: A list of tuple of the form (item id, variation id or None, number)
    :param session: Session ID of a guest
    """
    event = Event.objects.get(id=event)
    try:
        try:
            _remove_items_from_cart(event, items, cart_id)
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise CartError(error_messages['busy'])
