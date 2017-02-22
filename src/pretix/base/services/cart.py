from collections import Counter, namedtuple
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from pretix.base.decimal import round_decimal
from pretix.base.i18n import LazyLocaleException
from pretix.base.models import (
    CartPosition, Event, Item, ItemVariation, Voucher,
)
from pretix.base.services.async import ProfiledTask
from pretix.base.services.locking import LockTimeoutException
from pretix.celery_app import app


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


class CartManager:
    AddOperation = namedtuple('AddOperation', ('count', 'item', 'variation', 'price', 'voucher', 'quotas'))
    RemoveOperation = namedtuple('RemoveOperation', ('position',))
    ExtendOperation = namedtuple('ExtendOperation', ('position', 'count', 'item', 'variation', 'price', 'voucher',
                                                     'quotas'))
    order = {
        RemoveOperation: 10,
        ExtendOperation: 20,
        AddOperation: 30
    }

    def __init__(self, event: Event, cart_id: str):
        self.event = event
        self.cart_id = cart_id
        self.now_dt = now()
        self._operations = []
        self._quota_diff = Counter()
        self._voucher_use_diff = Counter()
        self._items_cache = {}
        self._variations_cache = {}
        self._expiry = None

    @property
    def positions(self):
        return CartPosition.objects.filter(
            Q(cart_id=self.cart_id) & Q(event=self.event)
        )

    def _calculate_expiry(self):
        self._expiry = self.now_dt + timedelta(minutes=self.event.settings.get('reservation_time', as_type=int))

    def _check_presale_dates(self):
        if self.event.presale_start and self.now_dt < self.event.presale_start:
            raise CartError(error_messages['not_started'])
        if self.event.presale_end and self.now_dt > self.event.presale_end:
            raise CartError(error_messages['ended'])

    def _extend_expiry_of_valid_existing_positions(self):
        # Extend this user's cart session to ensure all items in the cart expire at the same time
        # We can extend the reservation of items which are not yet expired without risk
        self.positions.filter(expires__gt=self.now_dt).update(expires=self._expiry)

    def _delete_expired(self, expired: List[CartPosition]):
        for cp in expired:
            if cp.expires <= self.now_dt:
                cp.delete()

    def _update_items_cache(self, item_ids: List[int], variation_ids: List[int]):
        self._items_cache.update(
            {i.pk: i for i in self.event.items.prefetch_related('quotas').filter(
                id__in=[i for i in item_ids if i and i not in self._items_cache]
            )}
        )
        self._variations_cache.update(
            {v.pk: v for v in
             ItemVariation.objects.filter(item__event=self.event).prefetch_related(
                 'quotas'
             ).select_related('item', 'item__event').filter(
                 id__in=[i for i in variation_ids if i and i not in self._variations_cache]
             )}
        )

    def _check_max_cart_size(self):
        cartsize = self.positions.count()
        cartsize += sum([op.count for op in self._operations if isinstance(op, self.AddOperation)])
        cartsize -= len([1 for op in self._operations if isinstance(op, self.RemoveOperation)])
        if cartsize > int(self.event.settings.max_items_per_order):
            # TODO: i18n plurals
            raise CartError(error_messages['max_items'], (self.event.settings.max_items_per_order,))

    def _check_item_constraints(self, op):
        if isinstance(op, self.AddOperation) or isinstance(op, self.ExtendOperation):
            if op.item.require_voucher and op.voucher is None:
                raise CartError(error_messages['voucher_required'])

            if op.item.hide_without_voucher and (op.voucher is None or op.voucher.item is None or op.voucher.item.pk != op.item.pk):
                raise CartError(error_messages['voucher_required'])

            if not op.item.is_available() or (op.variation and not op.variation.active):
                raise CartError(error_messages['unavailable'])

            if op.voucher and not op.voucher.applies_to(op.item, op.variation):
                raise CartError(error_messages['voucher_invalid_item'])

    def _get_price(self, item: Item, variation: Optional[ItemVariation],
                   voucher: Optional[Voucher], custom_price: Optional[Decimal]):
        price = item.default_price if variation is None else (
            variation.default_price if variation.default_price is not None else item.default_price
        )
        if voucher:
            price = voucher.calculate_price(price)

        if item.free_price and custom_price is not None and custom_price != "":
            if not isinstance(custom_price, Decimal):
                custom_price = Decimal(custom_price.replace(",", "."))
            if custom_price > 100000000:
                return error_messages['price_too_high']
            if self.event.settings.display_net_prices:
                custom_price = round_decimal(custom_price * (100 + item.tax_rate) / 100)
            price = max(custom_price, price)

        return price

    def extend_expired_positions(self):
        expired = self.positions.filter(expires__lte=self.now_dt).select_related(
            'item', 'variation', 'voucher'
        ).prefetch_related('item__quotas', 'variation__quotas')
        for cp in expired:
            price = self._get_price(cp.item, cp.variation, cp.voucher, cp.price)

            quotas = list(cp.item.quotas.all()) if cp.variation is None else list(cp.variation.quotas.all())
            if not quotas:
                raise CartError(error_messages['unavailable'])
            if not cp.voucher or (not cp.voucher.allow_ignore_quota and not cp.voucher.block_quota):
                for quota in quotas:
                    self._quota_diff[quota] += 1
            else:
                quotas = []

            op = self.ExtendOperation(
                position=cp, item=cp.item, variation=cp.variation, voucher=cp.voucher, count=1,
                price=price, quotas=quotas
            )
            self._check_item_constraints(op)

            if cp.voucher:
                self._voucher_use_diff[cp.voucher] += 1

            self._operations.append(op)

    def add_new_items(self, items: List[dict]):
        # Fetch items from the database
        self._update_items_cache([i['item'] for i in items], [i['variation'] for i in items])
        quota_diff = Counter()
        voucher_use_diff = Counter()
        operations = []

        for i in items:
            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if i['item'] not in self._items_cache or (i['variation'] and i['variation'] not in self._variations_cache):
                raise CartError(error_messages['not_for_sale'])

            item = self._items_cache[i['item']]
            variation = self._variations_cache[i['variation']] if i['variation'] is not None else None
            voucher = None

            if i.get('voucher'):
                try:
                    voucher = self.event.vouchers.get(code=i.get('voucher').strip())
                except Voucher.DoesNotExist:
                    raise CartError(error_messages['voucher_invalid'])
                else:
                    voucher_use_diff[voucher] += i['count']

            # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.

            quotas = list(item.quotas.all()) if variation is None else list(variation.quotas.all())
            if not quotas:
                raise CartError(error_messages['unavailable'])
            if not voucher or (not voucher.allow_ignore_quota and not voucher.block_quota):
                for quota in quotas:
                    quota_diff[quota] += i['count']
            else:
                quotas = []

            price = self._get_price(item, variation, voucher, i.get('price'))
            op = self.AddOperation(
                count=i['count'], item=item, variation=variation, price=price, voucher=voucher, quotas=quotas
            )
            self._check_item_constraints(op)
            operations.append(op)

        self._quota_diff += quota_diff
        self._voucher_use_diff += voucher_use_diff
        self._operations += operations

    def remove_items(self, items: List[dict]):
        # TODO: We could calculate quotadiffs and voucherdiffs here, which would lead to more
        # flexible usages (e.g. a RemoveOperation and an AddOperation in the same transaction
        # could cancel each other out quota-wise). However, we are not taking this performance
        # penalty for now as there is currently no outside interface that would allow building
        # such a transaction.
        for i in items:
            cw = Q(cart_id=self.cart_id) & Q(item_id=i['item']) & Q(event=self.event)
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
                    self._operations.append(self.RemoveOperation(position=cp))
                cnt -= len(correctprice)
            if cnt > 0:
                for cp in CartPosition.objects.filter(cw).order_by("-price")[:cnt]:
                    self._operations.append(self.RemoveOperation(position=cp))

    def _get_quota_availability(self):
        quotas_ok = {}
        for quota, count in self._quota_diff.items():
            avail = quota.availability(self.now_dt)
            if avail[1] is not None and avail[1] < count:
                quotas_ok[quota] = min(count, avail[1])
            else:
                quotas_ok[quota] = count
        return quotas_ok

    def _get_voucher_availability(self):
        vouchers_ok = {}
        for voucher, count in self._voucher_use_diff.items():
            voucher.refresh_from_db()

            if voucher.valid_until is not None and voucher.valid_until < self.now_dt:
                raise CartError(error_messages['voucher_expired'])

            redeemed_in_carts = CartPosition.objects.filter(
                Q(voucher=voucher) & Q(event=self.event) &
                Q(expires__gte=self.now_dt)
            ).exclude(pk__in=[
                op.position.voucher_id for op in self._operations if isinstance(op, self.ExtendOperation)
            ])
            v_avail = voucher.max_usages - voucher.redeemed - redeemed_in_carts.count()
            vouchers_ok[voucher] = v_avail

        return vouchers_ok

    def _perform_operations(self):
        vouchers_ok = self._get_voucher_availability()
        quotas_ok = self._get_quota_availability()
        err = None
        new_cart_positions = []

        self._operations.sort(key=lambda a: self.order[type(a)])

        for op in self._operations:
            if isinstance(op, self.RemoveOperation):
                op.position.delete()

            elif isinstance(op, self.AddOperation) or isinstance(op, self.ExtendOperation):
                # Create a CartPosition for as much items as we can
                requested_count = quota_available_count = voucher_available_count = op.count

                if op.quotas:
                    quota_available_count = min(requested_count, min(quotas_ok[q] for q in op.quotas))

                if op.voucher:
                    voucher_available_count = min(voucher_available_count, vouchers_ok[op.voucher])

                if quota_available_count < 1:
                    err = err or error_messages['unavailable']
                elif quota_available_count < requested_count:
                    err = err or error_messages['in_part']

                if voucher_available_count < 1:
                    err = err or error_messages['voucher_redeemed']
                elif voucher_available_count < requested_count:
                    err = err or error_messages['voucher_redeemed_partial'] % voucher_available_count

                available_count = min(quota_available_count, voucher_available_count)

                for q in op.quotas:
                    quotas_ok[q] -= available_count
                if op.voucher:
                    vouchers_ok[op.voucher] -= available_count

                if isinstance(op, self.AddOperation):
                    for k in range(available_count):
                        new_cart_positions.append(CartPosition(
                            event=self.event, item=op.item, variation=op.variation,
                            price=op.price, expires=self._expiry,
                            cart_id=self.cart_id, voucher=op.voucher
                        ))
                elif isinstance(op, self.ExtendOperation):
                    if available_count == 1:
                        op.position.expires = self._expiry
                        op.position.price = op.price
                        op.position.save()
                    elif available_count == 0:
                        op.position.delete()
                    else:
                        raise AssertionError("ExtendOperation cannot affect more than one item")

        CartPosition.objects.bulk_create(new_cart_positions)
        return err

    def commit(self):
        self._check_presale_dates()
        self._check_max_cart_size()
        self._calculate_expiry()

        with self.event.lock() as now_dt:
            with transaction.atomic():
                self.now_dt = now_dt
                self._extend_expiry_of_valid_existing_positions()
                self.extend_expired_positions()
                err = self._perform_operations()
            if err:
                raise CartError(err)


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
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
            cm = CartManager(event=event, cart_id=cart_id)
            cm.add_new_items(items)
            cm.commit()
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise CartError(error_messages['busy'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
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
            cm = CartManager(event=event, cart_id=cart_id)
            cm.remove_items(items)
            cm.commit()
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise CartError(error_messages['busy'])
