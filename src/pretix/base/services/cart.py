from collections import Counter, defaultdict, namedtuple
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from celery.exceptions import MaxRetriesExceededError
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext as _

from pretix.base.i18n import language
from pretix.base.models import (
    CartPosition, Event, InvoiceAddress, Item, ItemVariation, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import OrderFee
from pretix.base.models.tax import TAXED_ZERO, TaxedPrice, TaxRule
from pretix.base.services.checkin import _save_answers
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.pricing import get_price
from pretix.base.services.tasks import ProfiledTask
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.templatetags.rich_text import rich_text
from pretix.celery_app import app
from pretix.presale.signals import (
    checkout_confirm_messages, fee_calculation_for_cart,
)


class CartError(Exception):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


error_messages = {
    'busy': _('We were not able to process your request completely as the '
              'server was too busy. Please try again.'),
    'empty': _('You did not select any products.'),
    'unknown_position': _('Unknown cart position.'),
    'subevent_required': pgettext_lazy('subevent', 'No date was specified.'),
    'not_for_sale': _('You selected a product which is not available for sale.'),
    'unavailable': _('Some of the products you selected are no longer available. '
                     'Please see below for details.'),
    'in_part': _('Some of the products you selected are no longer available in '
                 'the quantity you selected. Please see below for details.'),
    'max_items': _("You cannot select more than %s items per order."),
    'max_items_per_product': _("You cannot select more than %(max)s items of the product %(product)s."),
    'min_items_per_product': _("You need to select at least %(min)s items of the product %(product)s."),
    'min_items_per_product_removed': _("We removed %(product)s from your cart as you can not buy less than "
                                       "%(min)s items of it."),
    'not_started': _('The presale period for this event has not yet started.'),
    'ended': _('The presale period for this event has ended.'),
    'some_subevent_not_started': _('The presale period for this event has not yet started. The affected positions '
                                   'have been removed from your cart.'),
    'some_subevent_ended': _('The presale period for one of the events in your cart has ended. The affected '
                             'positions have been removed from your cart.'),
    'price_too_high': _('The entered price is to high.'),
    'voucher_invalid': _('This voucher code is not known in our database.'),
    'voucher_redeemed': _('This voucher code has already been used the maximum number of times allowed.'),
    'voucher_redeemed_cart': _('This voucher code is currently locked since it is already contained in a cart. This '
                               'might mean that someone else is redeeming this voucher right now, or that you tried '
                               'to redeem it before but did not complete the checkout process. You can try to use it '
                               'again in %d minutes.'),
    'voucher_redeemed_partial': _('This voucher code can only be redeemed %d more times.'),
    'voucher_double': _('You already used this voucher code. Remove the associated line from your '
                        'cart if you want to use it for a different product.'),
    'voucher_expired': _('This voucher is expired.'),
    'voucher_invalid_item': _('This voucher is not valid for this product.'),
    'voucher_item_not_available': _(
        'Your voucher is valid for a product that is currently not for sale.'),
    'voucher_invalid_subevent': pgettext_lazy('subevent', 'This voucher is not valid for this event date.'),
    'voucher_required': _('You need a valid voucher code to order this product.'),
    'inactive_subevent': pgettext_lazy('subevent', 'The selected event date is not active.'),
    'addon_invalid_base': _('You can not select an add-on for the selected product.'),
    'addon_duplicate_item': _('You can not select two variations of the same add-on product.'),
    'addon_max_count': _('You can select at most %(max)s add-ons from the category %(cat)s for the product %(base)s.'),
    'addon_min_count': _('You need to select at least %(min)s add-ons from the category %(cat)s for the '
                         'product %(base)s.'),
    'addon_only': _('One of the products you selected can only be bought as an add-on to another project.'),
}


class CartManager:
    AddOperation = namedtuple('AddOperation', ('count', 'item', 'variation', 'price', 'voucher', 'quotas',
                                               'addon_to', 'subevent', 'includes_tax'))
    RemoveOperation = namedtuple('RemoveOperation', ('position',))
    ExtendOperation = namedtuple('ExtendOperation', ('position', 'count', 'item', 'variation', 'price', 'voucher',
                                                     'quotas', 'subevent'))
    order = {
        RemoveOperation: 10,
        ExtendOperation: 20,
        AddOperation: 30
    }

    def __init__(self, event: Event, cart_id: str, invoice_address: InvoiceAddress=None, widget_data=None,
                 sales_channel='web'):
        self.event = event
        self.cart_id = cart_id
        self.now_dt = now()
        self._operations = []
        self._quota_diff = Counter()
        self._voucher_use_diff = Counter()
        self._items_cache = {}
        self._subevents_cache = {}
        self._variations_cache = {}
        self._expiry = None
        self.invoice_address = invoice_address
        self._widget_data = widget_data or {}
        self._sales_channel = sales_channel

    @property
    def positions(self):
        return CartPosition.objects.filter(
            Q(cart_id=self.cart_id) & Q(event=self.event)
        ).select_related('item', 'subevent')

    def _calculate_expiry(self):
        self._expiry = self.now_dt + timedelta(minutes=self.event.settings.get('reservation_time', as_type=int))

    def _check_presale_dates(self):
        if self.event.presale_start and self.now_dt < self.event.presale_start:
            raise CartError(error_messages['not_started'])
        if self.event.presale_has_ended:
            raise CartError(error_messages['ended'])

    def _extend_expiry_of_valid_existing_positions(self):
        # Extend this user's cart session to ensure all items in the cart expire at the same time
        # We can extend the reservation of items which are not yet expired without risk
        self.positions.filter(expires__gt=self.now_dt).update(expires=self._expiry)

    def _delete_out_of_timeframe(self):
        err = None
        for cp in self.positions:
            if cp.subevent and cp.subevent.presale_start and self.now_dt < cp.subevent.presale_start:
                err = error_messages['some_subevent_not_started']
                cp.addons.all().delete()
                cp.delete()

            if cp.subevent and cp.subevent.presale_end and self.now_dt > cp.subevent.presale_end:
                err = error_messages['some_subevent_ended']
                cp.addons.all().delete()
                cp.delete()
        return err

    def _update_subevents_cache(self, se_ids: List[int]):
        self._subevents_cache.update({
            i.pk: i
            for i in self.event.subevents.filter(id__in=[i for i in se_ids if i and i not in self._items_cache])
        })

    def _update_items_cache(self, item_ids: List[int], variation_ids: List[int]):
        self._items_cache.update({
            i.pk: i
            for i in self.event.items.select_related('category').prefetch_related(
                'addons', 'addons__addon_category', 'quotas'
            ).filter(
                id__in=[i for i in item_ids if i and i not in self._items_cache]
            )
        })
        self._variations_cache.update({
            v.pk: v
            for v in ItemVariation.objects.filter(item__event=self.event).prefetch_related(
                'quotas'
            ).select_related('item', 'item__event').filter(
                id__in=[i for i in variation_ids if i and i not in self._variations_cache]
            )
        })

    def _check_max_cart_size(self):
        cartsize = self.positions.filter(addon_to__isnull=True).count()
        cartsize += sum([op.count for op in self._operations if isinstance(op, self.AddOperation) and not op.addon_to])
        cartsize -= len([1 for op in self._operations if isinstance(op, self.RemoveOperation) if
                         not op.position.addon_to_id])
        if cartsize > int(self.event.settings.max_items_per_order):
            # TODO: i18n plurals
            raise CartError(_(error_messages['max_items']) % (self.event.settings.max_items_per_order,))

    def _check_item_constraints(self, op):
        if isinstance(op, self.AddOperation) or isinstance(op, self.ExtendOperation):
            if op.item.require_voucher and op.voucher is None:
                raise CartError(error_messages['voucher_required'])

            if op.item.hide_without_voucher and (op.voucher is None or op.voucher.item is None or op.voucher.item.pk != op.item.pk):
                raise CartError(error_messages['voucher_required'])

            if not op.item.is_available() or (op.variation and not op.variation.active):
                raise CartError(error_messages['unavailable'])

            if self._sales_channel not in op.item.sales_channels:
                raise CartError(error_messages['unavailable'])

            if op.voucher and not op.voucher.applies_to(op.item, op.variation):
                raise CartError(error_messages['voucher_invalid_item'])

            if op.voucher and op.voucher.subevent_id and op.voucher.subevent_id != op.subevent.pk:
                raise CartError(error_messages['voucher_invalid_subevent'])

            if op.subevent and not op.subevent.active:
                raise CartError(error_messages['inactive_subevent'])

            if op.subevent and op.subevent.presale_start and self.now_dt < op.subevent.presale_start:
                raise CartError(error_messages['not_started'])

            if op.subevent and op.subevent.presale_has_ended:
                raise CartError(error_messages['ended'])

        if isinstance(op, self.AddOperation):
            if op.item.category and op.item.category.is_addon and not op.addon_to:
                raise CartError(error_messages['addon_only'])

            if op.item.max_per_order or op.item.min_per_order:
                new_total = (
                    len([1 for p in self.positions if p.item_id == op.item.pk]) +
                    sum([_op.count for _op in self._operations
                         if isinstance(_op, self.AddOperation) and _op.item == op.item]) +
                    op.count -
                    len([1 for _op in self._operations
                         if isinstance(_op, self.RemoveOperation) and _op.position.item_id == op.item.pk])
                )

            if op.item.max_per_order and new_total > op.item.max_per_order:
                raise CartError(
                    _(error_messages['max_items_per_product']) % {
                        'max': op.item.max_per_order,
                        'product': op.item.name
                    }
                )

            if op.item.min_per_order and new_total < op.item.min_per_order:
                raise CartError(
                    _(error_messages['min_items_per_product']) % {
                        'min': op.item.min_per_order,
                        'product': op.item.name
                    }
                )

    def _get_price(self, item: Item, variation: Optional[ItemVariation],
                   voucher: Optional[Voucher], custom_price: Optional[Decimal],
                   subevent: Optional[SubEvent], cp_is_net: bool=None):
        try:
            return get_price(
                item, variation, voucher, custom_price, subevent,
                custom_price_is_net=cp_is_net if cp_is_net is not None else self.event.settings.display_net_prices,
                invoice_address=self.invoice_address
            )
        except ValueError as e:
            if str(e) == 'price_too_high':
                raise CartError(error_messages['price_too_high'])
            else:
                raise e

    def extend_expired_positions(self):
        expired = self.positions.filter(expires__lte=self.now_dt).select_related(
            'item', 'variation', 'voucher'
        ).prefetch_related('item__quotas', 'variation__quotas')
        err = None
        for cp in expired:
            if not cp.includes_tax:
                price = self._get_price(cp.item, cp.variation, cp.voucher, cp.price, cp.subevent,
                                        cp_is_net=True)
                price = TaxedPrice(net=price.net, gross=price.net, rate=0, tax=0, name='')
            else:
                price = self._get_price(cp.item, cp.variation, cp.voucher, cp.price, cp.subevent)

            quotas = list(cp.quotas)
            if not quotas:
                self._operations.append(self.RemoveOperation(position=cp))
                continue
                err = error_messages['unavailable']

            if not cp.voucher or (not cp.voucher.allow_ignore_quota and not cp.voucher.block_quota):
                for quota in quotas:
                    self._quota_diff[quota] += 1
            else:
                quotas = []

            op = self.ExtendOperation(
                position=cp, item=cp.item, variation=cp.variation, voucher=cp.voucher, count=1,
                price=price, quotas=quotas, subevent=cp.subevent
            )
            self._check_item_constraints(op)

            if cp.voucher:
                self._voucher_use_diff[cp.voucher] += 1

            self._operations.append(op)
        return err

    def add_new_items(self, items: List[dict]):
        # Fetch items from the database
        self._update_items_cache([i['item'] for i in items], [i['variation'] for i in items])
        self._update_subevents_cache([i['subevent'] for i in items if i.get('subevent')])
        quota_diff = Counter()
        voucher_use_diff = Counter()
        operations = []

        for i in items:
            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if i['item'] not in self._items_cache or (i['variation'] and i['variation'] not in self._variations_cache):
                raise CartError(error_messages['not_for_sale'])

            if self.event.has_subevents:
                if not i.get('subevent'):
                    raise CartError(error_messages['subevent_required'])
                subevent = self._subevents_cache[int(i.get('subevent'))]
            else:
                subevent = None

            item = self._items_cache[i['item']]
            variation = self._variations_cache[i['variation']] if i['variation'] is not None else None
            voucher = None

            if i.get('voucher'):
                try:
                    voucher = self.event.vouchers.get(code__iexact=i.get('voucher').strip())
                except Voucher.DoesNotExist:
                    raise CartError(error_messages['voucher_invalid'])
                else:
                    voucher_use_diff[voucher] += i['count']

            # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
            quotas = list(item.quotas.filter(subevent=subevent)
                          if variation is None else variation.quotas.filter(subevent=subevent))
            if not quotas:
                raise CartError(error_messages['unavailable'])
            if not voucher or (not voucher.allow_ignore_quota and not voucher.block_quota):
                for quota in quotas:
                    quota_diff[quota] += i['count']
            else:
                quotas = []

            price = self._get_price(item, variation, voucher, i.get('price'), subevent)
            op = self.AddOperation(
                count=i['count'], item=item, variation=variation, price=price, voucher=voucher, quotas=quotas,
                addon_to=False, subevent=subevent, includes_tax=bool(price.rate)
            )
            self._check_item_constraints(op)
            operations.append(op)

        self._quota_diff.update(quota_diff)
        self._voucher_use_diff += voucher_use_diff
        self._operations += operations

    def remove_item(self, pos_id: int):
        # TODO: We could calculate quotadiffs and voucherdiffs here, which would lead to more
        # flexible usages (e.g. a RemoveOperation and an AddOperation in the same transaction
        # could cancel each other out quota-wise). However, we are not taking this performance
        # penalty for now as there is currently no outside interface that would allow building
        # such a transaction.
        try:
            cp = self.positions.get(pk=pos_id)
        except CartPosition.DoesNotExist:
            raise CartError(error_messages['unknown_position'])
        self._operations.append(self.RemoveOperation(position=cp))

    def clear(self):
        # TODO: We could calculate quotadiffs and voucherdiffs here, which would lead to more
        # flexible usages (e.g. a RemoveOperation and an AddOperation in the same transaction
        # could cancel each other out quota-wise). However, we are not taking this performance
        # penalty for now as there is currently no outside interface that would allow building
        # such a transaction.
        for cp in self.positions.filter(addon_to__isnull=True):
            self._operations.append(self.RemoveOperation(position=cp))

    def set_addons(self, addons):
        self._update_items_cache(
            [a['item'] for a in addons],
            [a['variation'] for a in addons],
        )

        # Prepare various containers to hold data later
        current_addons = defaultdict(dict)  # CartPos -> currently attached add-ons
        input_addons = defaultdict(set)  # CartPos -> add-ons according to input
        selected_addons = defaultdict(set)  # CartPos -> final desired set of add-ons
        cpcache = {}  # CartPos.pk -> CartPos
        quota_diff = Counter()  # Quota -> Number of usages
        operations = []
        available_categories = defaultdict(set)  # CartPos -> Category IDs to choose from
        price_included = defaultdict(dict)  # CartPos -> CategoryID -> bool(price is included)
        toplevel_cp = self.positions.filter(
            addon_to__isnull=True
        ).prefetch_related(
            'addons', 'item__addons', 'item__addons__addon_category'
        ).select_related('item', 'variation')

        # Prefill some of the cache containers
        for cp in toplevel_cp:
            available_categories[cp.pk] = {iao.addon_category_id for iao in cp.item.addons.all()}
            price_included[cp.pk] = {iao.addon_category_id: iao.price_included for iao in cp.item.addons.all()}
            cpcache[cp.pk] = cp
            current_addons[cp] = {
                (a.item_id, a.variation_id): a
                for a in cp.addons.all()
            }

        # Create operations, perform various checks
        for a in addons:
            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if a['item'] not in self._items_cache or (a['variation'] and a['variation'] not in self._variations_cache):
                raise CartError(error_messages['not_for_sale'])

            # Only attach addons to things that are actually in this user's cart
            if a['addon_to'] not in cpcache:
                raise CartError(error_messages['addon_invalid_base'])

            cp = cpcache[a['addon_to']]
            item = self._items_cache[a['item']]
            variation = self._variations_cache[a['variation']] if a['variation'] is not None else None

            if item.category_id not in available_categories[cp.pk]:
                raise CartError(error_messages['addon_invalid_base'])

            # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
            quotas = list(item.quotas.filter(subevent=cp.subevent)
                          if variation is None else variation.quotas.filter(subevent=cp.subevent))
            if not quotas:
                raise CartError(error_messages['unavailable'])

            # Every item can be attached to very CartPosition at most once
            if a['item'] in ([_a[0] for _a in input_addons[cp.id]]):
                raise CartError(error_messages['addon_duplicate_item'])

            input_addons[cp.id].add((a['item'], a['variation']))
            selected_addons[cp.id, item.category_id].add((a['item'], a['variation']))

            if (a['item'], a['variation']) not in current_addons[cp]:
                # This add-on is new, add it to the cart
                for quota in quotas:
                    quota_diff[quota] += 1

                if price_included[cp.pk].get(item.category_id):
                    price = TAXED_ZERO
                else:
                    price = self._get_price(item, variation, None, None, cp.subevent)

                op = self.AddOperation(
                    count=1, item=item, variation=variation, price=price, voucher=None, quotas=quotas,
                    addon_to=cp, subevent=cp.subevent, includes_tax=bool(price.rate)
                )
                self._check_item_constraints(op)
                operations.append(op)

        # Check constraints on the add-on combinations
        for cp in toplevel_cp:
            item = cp.item
            for iao in item.addons.all():
                selected = selected_addons[cp.id, iao.addon_category_id]
                if len(selected) > iao.max_count:
                    # TODO: Proper i18n
                    # TODO: Proper pluralization
                    raise CartError(
                        error_messages['addon_max_count'],
                        {
                            'base': str(item.name),
                            'max': iao.max_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )
                elif len(selected) < iao.min_count:
                    # TODO: Proper i18n
                    # TODO: Proper pluralization
                    raise CartError(
                        error_messages['addon_min_count'],
                        {
                            'base': str(item.name),
                            'min': iao.min_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )

        # Detect removed add-ons and create RemoveOperations
        for cp, al in current_addons.items():
            for k, v in al.items():
                if k not in input_addons[cp.id]:
                    if v.expires > self.now_dt:
                        quotas = list(v.quotas)

                        for quota in quotas:
                            quota_diff[quota] -= 1

                    op = self.RemoveOperation(position=v)
                    operations.append(op)

        self._quota_diff.update(quota_diff)
        self._operations += operations

    def _get_quota_availability(self):
        quotas_ok = defaultdict(int)
        for quota, count in self._quota_diff.items():
            if count <= 0:
                quotas_ok[quota] = 0
            avail = quota.availability(self.now_dt)
            if avail[1] is not None and avail[1] < count:
                quotas_ok[quota] = min(count, avail[1])
            else:
                quotas_ok[quota] = count
        return quotas_ok

    def _get_voucher_availability(self):
        vouchers_ok = {}
        self._voucher_depend_on_cart = set()
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
            cart_count = redeemed_in_carts.count()
            v_avail = voucher.max_usages - voucher.redeemed - cart_count
            if cart_count > 0:
                self._voucher_depend_on_cart.add(voucher)
            vouchers_ok[voucher] = v_avail

        return vouchers_ok

    def _check_min_per_product(self):
        per_product = Counter()
        min_per_product = {}
        for p in self.positions:
            per_product[p.item_id] += 1
            min_per_product[p.item.pk] = p.item.min_per_order

        for op in self._operations:
            if isinstance(op, self.AddOperation):
                per_product[op.item.pk] += op.count
                min_per_product[op.item.pk] = op.item.min_per_order
            elif isinstance(op, self.RemoveOperation):
                per_product[op.position.item_id] -= 1
                min_per_product[op.position.item.pk] = op.position.item.min_per_order

        err = None
        for itemid, num in per_product.items():
            min_p = min_per_product[itemid]
            if min_p and num < min_p:
                self._operations = [o for o in self._operations if not (
                    isinstance(o, self.AddOperation) and o.item.pk == itemid
                )]
                removals = [o.position.pk for o in self._operations if isinstance(o, self.RemoveOperation)]
                for p in self.positions:
                    if p.item_id == itemid and p.pk not in removals:
                        self._operations.append(self.RemoveOperation(position=p))
                        err = _(error_messages['min_items_per_product_removed']) % {
                            'min': min_p,
                            'product': p.item.name
                        }

        return err

    def _perform_operations(self):
        vouchers_ok = self._get_voucher_availability()
        quotas_ok = self._get_quota_availability()
        err = None
        new_cart_positions = []

        err = err or self._check_min_per_product()

        self._operations.sort(key=lambda a: self.order[type(a)])

        for op in self._operations:
            if isinstance(op, self.RemoveOperation):
                if op.position.expires > self.now_dt:
                    for q in op.position.quotas:
                        quotas_ok[q] += 1
                op.position.addons.all().delete()
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
                    if op.voucher in self._voucher_depend_on_cart:
                        err = err or error_messages['voucher_redeemed_cart'] % self.event.settings.reservation_time
                    else:
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
                        cp = CartPosition(
                            event=self.event, item=op.item, variation=op.variation,
                            price=op.price.gross, expires=self._expiry, cart_id=self.cart_id,
                            voucher=op.voucher, addon_to=op.addon_to if op.addon_to else None,
                            subevent=op.subevent, includes_tax=op.includes_tax
                        )
                        if self.event.settings.attendee_names_asked:
                            scheme = PERSON_NAME_SCHEMES.get(self.event.settings.name_scheme)
                            if 'attendee-name' in self._widget_data:
                                cp.attendee_name_parts = {'_legacy': self._widget_data['attendee-name']}
                            if any('attendee-name-{}'.format(k.replace('_', '-')) in self._widget_data for k, l, w
                                   in scheme['fields']):
                                cp.attendee_name_parts = {
                                    k: self._widget_data.get('attendee-name-{}'.format(k.replace('_', '-')), '')
                                    for k, l, w in scheme['fields']
                                }
                        if self.event.settings.attendee_emails_asked and 'email' in self._widget_data:
                            cp.attendee_email = self._widget_data.get('email')

                        cp._answers = {}
                        for k, v in self._widget_data.items():
                            if not k.startswith('question-'):
                                continue
                            q = cp.item.questions.filter(ask_during_checkin=False, identifier__iexact=k[9:]).first()
                            if q:
                                try:
                                    cp._answers[q] = q.clean_answer(v)
                                except ValidationError:
                                    pass

                        new_cart_positions.append(cp)
                elif isinstance(op, self.ExtendOperation):
                    if available_count == 1:
                        op.position.expires = self._expiry
                        op.position.price = op.price.gross
                        op.position.save()
                    elif available_count == 0:
                        op.position.addons.all().delete()
                        op.position.delete()
                    else:
                        raise AssertionError("ExtendOperation cannot affect more than one item")

        for p in new_cart_positions:
            if p._answers:
                p.save()
                _save_answers(p, {}, p._answers)
        CartPosition.objects.bulk_create([p for p in new_cart_positions if not p._answers])
        return err

    def commit(self):
        self._check_presale_dates()
        self._check_max_cart_size()
        self._calculate_expiry()

        with self.event.lock() as now_dt:
            with transaction.atomic():
                self.now_dt = now_dt
                self._extend_expiry_of_valid_existing_positions()
                err = self._delete_out_of_timeframe()
                err = self.extend_expired_positions() or err
                err = self._perform_operations() or err
            if err:
                raise CartError(err)


def update_tax_rates(event: Event, cart_id: str, invoice_address: InvoiceAddress):
    positions = CartPosition.objects.filter(
        cart_id=cart_id, event=event
    ).select_related('item', 'item__tax_rule')
    totaldiff = Decimal('0.00')
    for pos in positions:
        if not pos.item.tax_rule:
            continue
        charge_tax = pos.item.tax_rule.tax_applicable(invoice_address)
        if pos.includes_tax and not charge_tax:
            price = pos.item.tax(pos.price, base_price_is='gross').net
            totaldiff += price - pos.price
            pos.price = price
            pos.includes_tax = False
            pos.save(update_fields=['price', 'includes_tax'])
        elif charge_tax and not pos.includes_tax:
            price = pos.item.tax(pos.price, base_price_is='net').gross
            totaldiff += price - pos.price
            pos.price = price
            pos.includes_tax = True
            pos.save(update_fields=['price', 'includes_tax'])

    return totaldiff


def get_fees(event, request, total, invoice_address, provider):
    fees = []

    if provider and total != 0:
        provider = event.get_payment_providers().get(provider)
        if provider:
            payment_fee = provider.calculate_fee(total)

            if payment_fee:
                payment_fee_tax_rule = event.settings.tax_rate_default or TaxRule.zero()
                if payment_fee_tax_rule.tax_applicable(invoice_address):
                    payment_fee_tax = payment_fee_tax_rule.tax(payment_fee, base_price_is='gross')
                    fees.append(OrderFee(
                        fee_type=OrderFee.FEE_TYPE_PAYMENT,
                        value=payment_fee,
                        tax_rate=payment_fee_tax.rate,
                        tax_value=payment_fee_tax.tax,
                        tax_rule=payment_fee_tax_rule
                    ))
                else:
                    fees.append(OrderFee(
                        fee_type=OrderFee.FEE_TYPE_PAYMENT,
                        value=payment_fee,
                        tax_rate=Decimal('0.00'),
                        tax_value=Decimal('0.00'),
                        tax_rule=payment_fee_tax_rule
                    ))

    for recv, resp in fee_calculation_for_cart.send(sender=event, request=request, invoice_address=invoice_address,
                                                    total=total):
        fees += resp

    return fees


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def add_items_to_cart(self, event: int, items: List[dict], cart_id: str=None, locale='en',
                      invoice_address: int=None, widget_data=None, sales_channel='web') -> None:
    """
    Adds a list of items to a user's cart.
    :param event: The event ID in question
    :param items: A list of dicts with the keys item, variation, number, custom_price, voucher
    :param cart_id: Session ID of a guest
    :raises CartError: On any error that occured
    """
    with language(locale):
        event = Event.objects.get(id=event)

        ia = False
        if invoice_address:
            try:
                ia = InvoiceAddress.objects.get(pk=invoice_address)
            except InvoiceAddress.DoesNotExist:
                pass

        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, invoice_address=ia, widget_data=widget_data,
                                 sales_channel=sales_channel)
                cm.add_new_items(items)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def remove_cart_position(self, event: int, position: int, cart_id: str=None, locale='en') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param position: A cart position ID
    :param session: Session ID of a guest
    """
    with language(locale):
        event = Event.objects.get(id=event)
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id)
                cm.remove_item(position)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def clear_cart(self, event: int, cart_id: str=None, locale='en') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param session: Session ID of a guest
    """
    with language(locale):
        event = Event.objects.get(id=event)
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id)
                cm.clear()
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def set_cart_addons(self, event: int, addons: List[dict], cart_id: str=None, locale='en',
                    invoice_address: int=None, sales_channel='web') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param addons: A list of dicts with the keys addon_to, item, variation
    :param session: Session ID of a guest
    """
    with language(locale):
        event = Event.objects.get(id=event)

        ia = False
        if invoice_address:
            try:
                ia = InvoiceAddress.objects.get(pk=invoice_address)
            except InvoiceAddress.DoesNotExist:
                pass
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, invoice_address=ia, sales_channel=sales_channel)
                cm.set_addons(addons)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@receiver(checkout_confirm_messages, dispatch_uid="cart_confirm_messages")
def confirm_messages(sender, *args, **kwargs):
    if not sender.settings.confirm_text:
        return {}

    return {
        'confirm_text': rich_text(str(sender.settings.confirm_text))
    }
