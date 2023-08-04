#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Ben Hagan, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import re
import uuid
from collections import Counter, defaultdict, namedtuple
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import List, Optional

from celery.exceptions import MaxRetriesExceededError
from django import forms
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Value
from django.dispatch import receiver
from django.utils.timezone import make_aware, now
from django.utils.translation import (
    gettext as _, gettext_lazy, ngettext_lazy, pgettext_lazy,
)
from django_scopes import scopes_disabled

from pretix.base.channels import get_all_sales_channels
from pretix.base.i18n import language
from pretix.base.media import MEDIA_TYPES
from pretix.base.models import (
    CartPosition, Event, InvoiceAddress, Item, ItemVariation, Seat,
    SeatCategoryMapping, Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import OrderFee
from pretix.base.models.tax import TaxRule
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.services.checkin import _save_answers
from pretix.base.services.locking import LockTimeoutException, NoLockManager
from pretix.base.services.pricing import (
    apply_discounts, get_line_price, get_listed_price, get_price,
    is_included_for_free,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.settings import PERSON_NAME_SCHEMES, LazyI18nStringList
from pretix.base.signals import validate_cart_addons
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
            # force msg to string to make sure lazy-translation is done in current locale-context
            # otherwise translation might happen in celery-context, which uses default-locale
            # also translate with _/gettext to keep it backwards compatible
            msg = _(str(msg))
        super().__init__(msg)


error_messages = {
    'busy': gettext_lazy(
        'We were not able to process your request completely as the '
        'server was too busy. Please try again.'
    ),
    'empty': gettext_lazy('You did not select any products.'),
    'unknown_position': gettext_lazy('Unknown cart position.'),
    'subevent_required': pgettext_lazy('subevent', 'No date was specified.'),
    'not_for_sale': gettext_lazy('You selected a product which is not available for sale.'),
    'unavailable': gettext_lazy(
        'Some of the products you selected are no longer available. '
        'Please see below for details.'
    ),
    'in_part': gettext_lazy(
        'Some of the products you selected are no longer available in '
        'the quantity you selected. Please see below for details.'
    ),
    'max_items': ngettext_lazy(
        "You cannot select more than %s item per order.",
        "You cannot select more than %s items per order."
    ),
    'max_items_per_product': ngettext_lazy(
        "You cannot select more than %(max)s item of the product %(product)s.",
        "You cannot select more than %(max)s items of the product %(product)s.",
        "max"
    ),
    'min_items_per_product': ngettext_lazy(
        "You need to select at least %(min)s item of the product %(product)s.",
        "You need to select at least %(min)s items of the product %(product)s.",
        "min"
    ),
    'min_items_per_product_removed': ngettext_lazy(
        "We removed %(product)s from your cart as you can not buy less than %(min)s item of it.",
        "We removed %(product)s from your cart as you can not buy less than %(min)s items of it.",
        "min"
    ),
    'not_started': gettext_lazy('The booking period for this event has not yet started.'),
    'ended': gettext_lazy('The booking period for this event has ended.'),
    'payment_ended': gettext_lazy('All payments for this event need to be confirmed already, so no new orders can be created.'),
    'some_subevent_not_started': gettext_lazy(
        'The booking period for this event has not yet started. The affected positions '
        'have been removed from your cart.'),
    'some_subevent_ended': gettext_lazy(
        'The booking period for one of the events in your cart has ended. The affected '
        'positions have been removed from your cart.'),
    'price_not_a_number': gettext_lazy('The entered price is not a number.'),
    'price_too_high': gettext_lazy('The entered price is to high.'),
    'voucher_invalid': gettext_lazy('This voucher code is not known in our database.'),
    'voucher_min_usages': ngettext_lazy(
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products.',
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products.',
        'number'
    ),
    'voucher_min_usages_removed': ngettext_lazy(
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products. '
        'We have therefore removed some positions from your cart that can no longer be purchased like this.',
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products. '
        'We have therefore removed some positions from your cart that can no longer be purchased like this.',
        'number'
    ),
    'voucher_redeemed': gettext_lazy('This voucher code has already been used the maximum number of times allowed.'),
    'voucher_redeemed_cart': gettext_lazy(
        'This voucher code is currently locked since it is already contained in a cart. This '
        'might mean that someone else is redeeming this voucher right now, or that you tried '
        'to redeem it before but did not complete the checkout process. You can try to use it '
        'again in %d minutes.'
    ),
    'voucher_redeemed_partial': gettext_lazy('This voucher code can only be redeemed %d more times.'),
    'voucher_whole_cart_not_combined': gettext_lazy('Applying a voucher to the whole cart should not be combined with other operations.'),
    'voucher_double': gettext_lazy(
        'You already used this voucher code. Remove the associated line from your '
        'cart if you want to use it for a different product.'
    ),
    'voucher_expired': gettext_lazy('This voucher is expired.'),
    'voucher_invalid_item': gettext_lazy('This voucher is not valid for this product.'),
    'voucher_invalid_seat': gettext_lazy('This voucher is not valid for this seat.'),
    'voucher_no_match': gettext_lazy(
        'We did not find any position in your cart that we could use this voucher for. If you want '
        'to add something new to your cart using that voucher, you can do so with the voucher '
        'redemption option on the bottom of the page.'
    ),
    'voucher_item_not_available': gettext_lazy(
        'Your voucher is valid for a product that is currently not for sale.'),
    'voucher_invalid_subevent': pgettext_lazy('subevent', 'This voucher is not valid for this event date.'),
    'voucher_required': gettext_lazy('You need a valid voucher code to order this product.'),
    'inactive_subevent': pgettext_lazy('subevent', 'The selected event date is not active.'),
    'addon_invalid_base': gettext_lazy('You can not select an add-on for the selected product.'),
    'addon_duplicate_item': gettext_lazy('You can not select two variations of the same add-on product.'),
    'addon_max_count': ngettext_lazy(
        'You can select at most %(max)s add-on from the category %(cat)s for the product %(base)s.',
        'You can select at most %(max)s add-ons from the category %(cat)s for the product %(base)s.',
        'max'
    ),
    'addon_min_count': ngettext_lazy(
        'You need to select at least %(min)s add-on from the category %(cat)s for the product %(base)s.',
        'You need to select at least %(min)s add-ons from the category %(cat)s for the product %(base)s.',
        'min'
    ),
    'addon_no_multi': gettext_lazy('You can select every add-ons from the category %(cat)s for the product %(base)s at most once.'),
    'addon_only': gettext_lazy('One of the products you selected can only be bought as an add-on to another product.'),
    'bundled_only': gettext_lazy('One of the products you selected can only be bought part of a bundle.'),
    'seat_required': gettext_lazy('You need to select a specific seat.'),
    'seat_invalid': gettext_lazy('Please select a valid seat.'),
    'seat_forbidden': gettext_lazy('You can not select a seat for this position.'),
    'seat_unavailable': gettext_lazy('The seat you selected has already been taken. Please select a different seat.'),
    'seat_multiple': gettext_lazy('You can not select the same seat multiple times.'),
    'gift_card': gettext_lazy("You entered a gift card instead of a voucher. Gift cards can be entered later on when you're asked for your payment details."),
    'country_blocked': gettext_lazy('One of the selected products is not available in the selected country.'),
    'media_usage_not_implemented': gettext_lazy('The configuration of this product requires mapping to a physical '
                                                'medium, which is currently not available online.'),
}


def _get_quota_availability(quota_diff, now_dt):
    quotas_ok = defaultdict(int)
    qa = QuotaAvailability()
    qa.queue(*[k for k, v in quota_diff.items() if v > 0])
    qa.compute(now_dt=now_dt)
    for quota, count in quota_diff.items():
        if count <= 0:
            quotas_ok[quota] = 0
            break
        avail = qa.results[quota]
        if avail[1] is not None and avail[1] < count:
            quotas_ok[quota] = min(count, avail[1])
        else:
            quotas_ok[quota] = count
    return quotas_ok


def _get_voucher_availability(event, voucher_use_diff, now_dt, exclude_position_ids):
    vouchers_ok = {}
    _voucher_depend_on_cart = set()
    for voucher, count in voucher_use_diff.items():
        voucher.refresh_from_db()

        if voucher.valid_until is not None and voucher.valid_until < now_dt:
            raise CartError(error_messages['voucher_expired'])

        redeemed_in_carts = CartPosition.objects.filter(
            Q(voucher=voucher) & Q(event=event) &
            Q(expires__gte=now_dt)
        ).exclude(pk__in=exclude_position_ids)
        cart_count = redeemed_in_carts.count()
        v_avail = voucher.max_usages - voucher.redeemed - cart_count
        if cart_count > 0:
            _voucher_depend_on_cart.add(voucher)
        vouchers_ok[voucher] = v_avail

    return vouchers_ok, _voucher_depend_on_cart


class CartManager:
    AddOperation = namedtuple('AddOperation', ('count', 'item', 'variation', 'voucher', 'quotas',
                                               'addon_to', 'subevent', 'bundled', 'seat', 'listed_price',
                                               'price_after_voucher', 'custom_price_input',
                                               'custom_price_input_is_net', 'voucher_ignored'))
    RemoveOperation = namedtuple('RemoveOperation', ('position',))
    VoucherOperation = namedtuple('VoucherOperation', ('position', 'voucher', 'price_after_voucher'))
    ExtendOperation = namedtuple('ExtendOperation', ('position', 'count', 'item', 'variation', 'voucher',
                                                     'quotas', 'subevent', 'seat', 'listed_price',
                                                     'price_after_voucher'))
    order = {
        RemoveOperation: 10,
        VoucherOperation: 15,
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
        self._seated_cache = {}
        self._expiry = None
        self.invoice_address = invoice_address
        self._widget_data = widget_data or {}
        self._sales_channel = sales_channel

    @property
    def positions(self):
        return self.event.cartposition_set.filter(
            Q(cart_id=self.cart_id)
        ).select_related('item', 'subevent')

    def _is_seated(self, item, subevent):
        if not self.event.settings.seating_choice:
            return False
        if (item, subevent) not in self._seated_cache:
            self._seated_cache[item, subevent] = item.seat_category_mappings.filter(subevent=subevent).exists()
        return self._seated_cache[item, subevent]

    def _calculate_expiry(self):
        self._expiry = self.now_dt + timedelta(minutes=self.event.settings.get('reservation_time', as_type=int))

    def _check_presale_dates(self):
        if self.event.presale_start and self.now_dt < self.event.presale_start:
            raise CartError(error_messages['not_started'])
        if self.event.presale_has_ended:
            raise CartError(error_messages['ended'])
        if not self.event.has_subevents:
            tlv = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
            if tlv:
                term_last = make_aware(datetime.combine(
                    tlv.datetime(self.event).date(),
                    time(hour=23, minute=59, second=59)
                ), self.event.timezone)
                if term_last < self.now_dt:
                    raise CartError(error_messages['payment_ended'])

    def _extend_expiry_of_valid_existing_positions(self):
        # Extend this user's cart session to ensure all items in the cart expire at the same time
        # We can extend the reservation of items which are not yet expired without risk
        self.positions.filter(expires__gt=self.now_dt).update(expires=self._expiry)

    def _delete_out_of_timeframe(self):
        err = None
        for cp in self.positions:
            if not cp.pk:
                continue

            if cp.subevent and cp.subevent.presale_start and self.now_dt < cp.subevent.presale_start:
                err = error_messages['some_subevent_not_started']
                cp.addons.all().delete()
                cp.delete()

            if cp.subevent and cp.subevent.presale_end and self.now_dt > cp.subevent.presale_end:
                err = error_messages['some_subevent_ended']
                cp.addons.all().delete()
                cp.delete()

            if cp.subevent:
                tlv = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
                if tlv:
                    term_last = make_aware(datetime.combine(
                        tlv.datetime(cp.subevent).date(),
                        time(hour=23, minute=59, second=59)
                    ), self.event.timezone)
                    if term_last < self.now_dt:
                        err = error_messages['some_subevent_ended']
                        cp.addons.all().delete()
                        cp.delete()
        return err

    def _update_subevents_cache(self, se_ids: List[int]):
        self._subevents_cache.update({
            i.pk: i
            for i in self.event.subevents.filter(id__in=[i for i in se_ids if i and i not in self._subevents_cache])
        })

    def _update_items_cache(self, item_ids: List[int], variation_ids: List[int]):
        self._items_cache.update({
            i.pk: i
            for i in self.event.items.select_related('category').prefetch_related(
                'addons', 'bundles', 'addons__addon_category', 'quotas'
            ).annotate(
                has_variations=Count('variations'),
            ).filter(
                id__in=[i for i in item_ids if i and i not in self._items_cache]
            ).order_by()
        })
        self._variations_cache.update({
            v.pk: v
            for v in ItemVariation.objects.filter(item__event=self.event).prefetch_related(
                'quotas'
            ).select_related('item', 'item__event').filter(
                id__in=[i for i in variation_ids if i and i not in self._variations_cache]
            ).order_by()
        })

    def _check_max_cart_size(self):
        if not get_all_sales_channels()[self._sales_channel].unlimited_items_per_order:
            cartsize = self.positions.filter(addon_to__isnull=True).count()
            cartsize += sum([op.count for op in self._operations if isinstance(op, self.AddOperation) and not op.addon_to])
            cartsize -= len([1 for op in self._operations if isinstance(op, self.RemoveOperation) if
                             not op.position.addon_to_id])
            if cartsize > int(self.event.settings.max_items_per_order):
                raise CartError(error_messages['max_items'] % self.event.settings.max_items_per_order)

    def _check_item_constraints(self, op, current_ops=[]):
        if isinstance(op, (self.AddOperation, self.ExtendOperation)):
            if not (
                (isinstance(op, self.AddOperation) and op.addon_to == 'FAKE') or
                (isinstance(op, self.ExtendOperation) and op.position.is_bundled)
            ):
                if op.item.require_voucher and op.voucher is None:
                    if getattr(op, 'voucher_ignored', False):
                        raise CartError(error_messages['voucher_redeemed'])
                    raise CartError(error_messages['voucher_required'])

                if (
                    (op.item.hide_without_voucher or (op.variation and op.variation.hide_without_voucher)) and
                    (op.voucher is None or not op.voucher.show_hidden_items)
                ):
                    if getattr(op, 'voucher_ignored', False):
                        raise CartError(error_messages['voucher_redeemed'])
                    raise CartError(error_messages['voucher_required'])

            if not op.item.is_available() or (op.variation and not op.variation.is_available()):
                raise CartError(error_messages['unavailable'])

            if op.item.media_policy in (Item.MEDIA_POLICY_NEW, Item.MEDIA_POLICY_REUSE_OR_NEW):
                mt = MEDIA_TYPES[op.item.media_type]
                if not mt.medium_created_by_server:
                    raise CartError(error_messages['media_usage_not_implemented'])
            elif op.item.media_policy == Item.MEDIA_POLICY_REUSE:
                raise CartError(error_messages['media_usage_not_implemented'])

            if self._sales_channel not in op.item.sales_channels or (op.variation and self._sales_channel not in op.variation.sales_channels):
                raise CartError(error_messages['unavailable'])

            if op.subevent and op.item.pk in op.subevent.item_overrides and not op.subevent.item_overrides[op.item.pk].is_available():
                raise CartError(error_messages['not_for_sale'])

            if op.subevent and op.variation and op.variation.pk in op.subevent.var_overrides and \
                    not op.subevent.var_overrides[op.variation.pk].is_available():
                raise CartError(error_messages['not_for_sale'])

            if op.item.has_variations and not op.variation:
                raise CartError(error_messages['not_for_sale'])

            if op.variation and op.variation.item_id != op.item.pk:
                raise CartError(error_messages['not_for_sale'])

            if op.voucher and not op.voucher.applies_to(op.item, op.variation):
                raise CartError(error_messages['voucher_invalid_item'])

            if op.voucher and op.voucher.seat and op.voucher.seat != op.seat:
                raise CartError(error_messages['voucher_invalid_seat'])

            if op.voucher and op.voucher.subevent_id and op.voucher.subevent_id != op.subevent.pk:
                raise CartError(error_messages['voucher_invalid_subevent'])

            if op.subevent and not op.subevent.active:
                raise CartError(error_messages['inactive_subevent'])

            if op.subevent and op.subevent.presale_start and self.now_dt < op.subevent.presale_start:
                raise CartError(error_messages['not_started'])

            if op.subevent and op.subevent.presale_has_ended:
                raise CartError(error_messages['ended'])

            seated = self._is_seated(op.item, op.subevent)
            if seated and (not op.seat or (op.seat.blocked and self._sales_channel not in self.event.settings.seating_allow_blocked_seats_for_channel)):
                raise CartError(error_messages['seat_invalid'])
            elif op.seat and not seated:
                raise CartError(error_messages['seat_forbidden'])
            elif op.seat and op.seat.product != op.item:
                raise CartError(error_messages['seat_invalid'])
            elif op.seat and op.count > 1:
                raise CartError('Invalid request: A seat can only be bought once.')

            if op.subevent:
                tlv = self.event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
                if tlv:
                    term_last = make_aware(datetime.combine(
                        tlv.datetime(op.subevent).date(),
                        time(hour=23, minute=59, second=59)
                    ), self.event.timezone)
                    if term_last < self.now_dt:
                        raise CartError(error_messages['payment_ended'])

        if isinstance(op, self.AddOperation):
            if op.item.category and op.item.category.is_addon and not (op.addon_to and op.addon_to != 'FAKE'):
                raise CartError(error_messages['addon_only'])

            if op.item.require_bundling and not op.addon_to == 'FAKE':
                raise CartError(error_messages['bundled_only'])

    def _get_price(self, item: Item, variation: Optional[ItemVariation],
                   voucher: Optional[Voucher], custom_price: Optional[Decimal],
                   subevent: Optional[SubEvent], cp_is_net: bool=None, force_custom_price=False,
                   bundled_sum=Decimal('0.00')):
        try:
            return get_price(
                item, variation, voucher, custom_price, subevent,
                custom_price_is_net=cp_is_net if cp_is_net is not None else self.event.settings.display_net_prices,
                invoice_address=self.invoice_address, force_custom_price=force_custom_price, bundled_sum=bundled_sum
            )
        except TaxRule.SaleNotAllowed:
            raise CartError(error_messages['country_blocked'])
        except ValueError as e:
            if str(e) == 'price_too_high':
                raise CartError(error_messages['price_too_high'])
            else:
                raise e

    def extend_expired_positions(self):
        requires_seat = Exists(
            SeatCategoryMapping.objects.filter(
                Q(product=OuterRef('item'))
                & (Q(subevent=OuterRef('subevent')) if self.event.has_subevents else Q(subevent__isnull=True))
            )
        )
        if not self.event.settings.seating_choice:
            requires_seat = Value(0, output_field=IntegerField())
        expired = self.positions.filter(expires__lte=self.now_dt).select_related(
            'item', 'variation', 'voucher', 'addon_to', 'addon_to__item'
        ).annotate(
            requires_seat=requires_seat
        ).prefetch_related(
            'item__quotas',
            'variation__quotas',
            'addons'
        ).order_by('-is_bundled')
        err = None
        for cp in expired:
            removed_positions = {op.position.pk for op in self._operations if isinstance(op, self.RemoveOperation)}
            if cp.pk in removed_positions or (cp.addon_to_id and cp.addon_to_id in removed_positions):
                continue

            cp.item.requires_seat = self.event.settings.seating_choice and cp.requires_seat

            if cp.is_bundled:
                bundle = cp.addon_to.item.bundles.filter(bundled_item=cp.item, bundled_variation=cp.variation).first()
                if bundle:
                    if cp.addon_to.voucher_id and cp.addon_to.voucher.all_bundles_included:
                        listed_price = Decimal('0.00')
                    else:
                        listed_price = bundle.designated_price
                else:
                    listed_price = cp.price
                price_after_voucher = listed_price
            else:
                if cp.addon_to_id and is_included_for_free(cp.item, cp.addon_to):
                    listed_price = Decimal('0.00')
                else:
                    listed_price = get_listed_price(cp.item, cp.variation, cp.subevent)
                if cp.voucher:
                    price_after_voucher = cp.voucher.calculate_price(listed_price)
                else:
                    price_after_voucher = listed_price

            quotas = list(cp.quotas)
            if not quotas:
                self._operations.append(self.RemoveOperation(position=cp))
                err = error_messages['unavailable']
                continue

            if not cp.voucher or (not cp.voucher.allow_ignore_quota and not cp.voucher.block_quota):
                for quota in quotas:
                    self._quota_diff[quota] += 1
            else:
                quotas = []

            op = self.ExtendOperation(
                position=cp, item=cp.item, variation=cp.variation, voucher=cp.voucher, count=1,
                quotas=quotas, subevent=cp.subevent, seat=cp.seat, listed_price=listed_price,
                price_after_voucher=price_after_voucher,
            )
            self._check_item_constraints(op)

            if cp.voucher:
                self._voucher_use_diff[cp.voucher] += 2

            self._operations.append(op)
        return err

    def apply_voucher(self, voucher_code: str):
        if self._operations:
            raise CartError(error_messages['voucher_whole_cart_not_combined'])
        try:
            voucher = self.event.vouchers.get(code__iexact=voucher_code.strip())
        except Voucher.DoesNotExist:
            if self.event.organizer.accepted_gift_cards.filter(secret__iexact=voucher_code).exists():
                raise CartError(error_messages['gift_card'])
            else:
                raise CartError(error_messages['voucher_invalid'])
        voucher_use_diff = Counter()
        ops = []

        if not voucher.is_active():
            raise CartError(error_messages['voucher_expired'])

        for p in self.positions:
            if p.voucher_id:
                continue

            if not voucher.applies_to(p.item, p.variation):
                continue

            if voucher.seat and voucher.seat != p.seat:
                continue

            if voucher.subevent_id and voucher.subevent_id != p.subevent_id:
                continue

            if p.is_bundled:
                continue

            if p.listed_price is None:
                if p.addon_to_id and is_included_for_free(p.item, p.addon_to):
                    listed_price = Decimal('0.00')
                else:
                    listed_price = get_listed_price(p.item, p.variation, p.subevent)
            else:
                listed_price = p.listed_price
            price_after_voucher = voucher.calculate_price(listed_price)

            voucher_use_diff[voucher] += 1
            ops.append((listed_price - price_after_voucher, self.VoucherOperation(p, voucher, price_after_voucher)))

        for voucher, cnt in list(voucher_use_diff.items()):
            if 0 < cnt < voucher.min_usages_remaining:
                raise CartError(
                    error_messages['voucher_min_usages'] % {
                        'voucher': voucher.code,
                        'number': voucher.min_usages_remaining,
                    }
                )

        # If there are not enough voucher usages left for the full cart, let's apply them in the order that benefits
        # the user the most.
        ops.sort(key=lambda k: k[0], reverse=True)
        self._operations += [k[1] for k in ops]

        if not voucher_use_diff:
            raise CartError(error_messages['voucher_no_match'])
        self._voucher_use_diff += voucher_use_diff

    def add_new_items(self, items: List[dict]):
        # Fetch items from the database
        self._update_items_cache([i['item'] for i in items], [i['variation'] for i in items])
        self._update_subevents_cache([i['subevent'] for i in items if i.get('subevent')])
        quota_diff = Counter()
        voucher_use_diff = Counter()
        operations = []

        for i in items:
            if self.event.has_subevents:
                if not i.get('subevent') or int(i.get('subevent')) not in self._subevents_cache:
                    raise CartError(error_messages['subevent_required'])
                subevent = self._subevents_cache[int(i.get('subevent'))]
            else:
                subevent = None

            # When a seat is given, we ignore the item that was given, since we can infer it from the
            # seat. The variation is still relevant, though!
            seat = None
            if i.get('seat'):
                try:
                    seat = (subevent or self.event).seats.get(seat_guid=i.get('seat'))
                except Seat.DoesNotExist:
                    raise CartError(error_messages['seat_invalid'])
                except Seat.MultipleObjectsReturned:
                    raise CartError(error_messages['seat_invalid'])
                i['item'] = seat.product_id
                if i['item'] not in self._items_cache:
                    self._update_items_cache([i['item']], [i['variation']])

            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if i['item'] not in self._items_cache or (i['variation'] and i['variation'] not in self._variations_cache):
                raise CartError(error_messages['not_for_sale'])

            item = self._items_cache[i['item']]
            variation = self._variations_cache[i['variation']] if i['variation'] is not None else None
            voucher = None
            voucher_ignored = False

            if i.get('voucher'):
                try:
                    voucher = self.event.vouchers.get(code__iexact=i.get('voucher').strip())
                except Voucher.DoesNotExist:
                    raise CartError(error_messages['voucher_invalid'])
                else:
                    voucher_use_diff[voucher] += i['count']

                    if i.get('voucher_ignore_if_redeemed', False):
                        # This is a special case handling for when a user clicks "+" on an existing line in their cart
                        # that has a voucher attached. If the voucher still has redemptions left, we'll add another line
                        # with the same voucher, but if it does not we silently continue as if there was no voucher,
                        # leading to either a higher-priced ticket or an error. Still, this leads to less error cases
                        # than either of the possible default assumptions.
                        predicted_redeemed_after = (
                            voucher.redeemed +
                            CartPosition.objects.filter(voucher=voucher, expires__gte=self.now_dt).count() +
                            self._voucher_use_diff[voucher] +
                            voucher_use_diff[voucher]
                        )
                        if predicted_redeemed_after > voucher.max_usages:
                            i.pop('voucher')
                            voucher_ignored = True
                            voucher = None
                            voucher_use_diff[voucher] -= i['count']

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

            # Fetch bundled items
            bundled = []
            db_bundles = list(item.bundles.all())
            self._update_items_cache([b.bundled_item_id for b in db_bundles], [b.bundled_variation_id for b in db_bundles])
            for bundle in db_bundles:
                if bundle.bundled_item_id not in self._items_cache or (
                        bundle.bundled_variation_id and bundle.bundled_variation_id not in self._variations_cache
                ):
                    raise CartError(error_messages['not_for_sale'])
                bitem = self._items_cache[bundle.bundled_item_id]
                bvar = self._variations_cache[bundle.bundled_variation_id] if bundle.bundled_variation_id else None
                bundle_quotas = list(bitem.quotas.filter(subevent=subevent)
                                     if bvar is None else bvar.quotas.filter(subevent=subevent))
                if not bundle_quotas:
                    raise CartError(error_messages['unavailable'])
                if not voucher or not voucher.allow_ignore_quota:
                    for quota in bundle_quotas:
                        quota_diff[quota] += bundle.count * i['count']
                else:
                    bundle_quotas = []

                if voucher and voucher.all_bundles_included:
                    bundled_price = Decimal('0.00')
                else:
                    bundled_price = bundle.designated_price

                bop = self.AddOperation(
                    count=bundle.count,
                    item=bitem,
                    variation=bvar,
                    voucher=None,
                    quotas=bundle_quotas,
                    addon_to='FAKE',
                    subevent=subevent,
                    bundled=[],
                    seat=None,
                    listed_price=bundled_price,
                    price_after_voucher=bundled_price,
                    custom_price_input=None,
                    custom_price_input_is_net=False,
                    voucher_ignored=False,
                )
                self._check_item_constraints(bop, operations)
                bundled.append(bop)

            listed_price = get_listed_price(item, variation, subevent)
            if voucher:
                price_after_voucher = voucher.calculate_price(listed_price)
            else:
                price_after_voucher = listed_price
            custom_price = None
            if item.free_price and i.get('price'):
                custom_price = re.sub('[^0-9.,]', '', str(i.get('price')))
                if not custom_price:
                    raise CartError(error_messages['price_not_a_number'])
                try:
                    custom_price = forms.DecimalField(localize=True).to_python(custom_price)
                except:
                    try:
                        custom_price = Decimal(custom_price)
                    except:
                        raise CartError(error_messages['price_not_a_number'])
                if custom_price > 99_999_999_999:
                    raise CartError(error_messages['price_too_high'])

            op = self.AddOperation(
                count=i['count'],
                item=item,
                variation=variation,
                voucher=voucher,
                quotas=quotas,
                addon_to=False,
                subevent=subevent,
                bundled=bundled,
                seat=seat,
                listed_price=listed_price,
                price_after_voucher=price_after_voucher,
                custom_price_input=custom_price,
                custom_price_input_is_net=self.event.settings.display_net_prices,
                voucher_ignored=voucher_ignored,
            )
            self._check_item_constraints(op, operations)
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
        current_addons = defaultdict(lambda: defaultdict(list))  # CartPos -> currently attached add-ons
        input_addons = defaultdict(Counter)  # CartPos -> final desired set of add-ons
        selected_addons = defaultdict(Counter)  # CartPos, ItemAddOn -> final desired set of add-ons
        cpcache = {}  # CartPos.pk -> CartPos
        quota_diff = Counter()  # Quota -> Number of usages
        operations = []
        available_categories = defaultdict(set)  # CartPos -> Category IDs to choose from
        toplevel_cp = self.positions.filter(
            addon_to__isnull=True
        ).prefetch_related(
            'addons', 'item__addons', 'item__addons__addon_category'
        ).select_related('item', 'variation')

        # Prefill some of the cache containers
        for cp in toplevel_cp:
            available_categories[cp.pk] = {iao.addon_category_id for iao in cp.item.addons.all()}
            cpcache[cp.pk] = cp
            for a in cp.addons.all():
                if not a.is_bundled:
                    current_addons[cp][a.item_id, a.variation_id].append(a)

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

            if (a['item'], a['variation']) in input_addons[cp.id]:
                raise CartError(error_messages['addon_duplicate_item'])

            input_addons[cp.id][a['item'], a['variation']] = a.get('count', 1)
            selected_addons[cp.id, item.category_id][a['item'], a['variation']] = a.get('count', 1)

            if is_included_for_free(item, cp):
                listed_price = Decimal('0.00')
            else:
                listed_price = get_listed_price(item, variation, cp.subevent)
            custom_price = None
            if item.free_price and a.get('price'):
                custom_price = re.sub('[^0-9.,]', '', a.get('price'))
                if not custom_price:
                    raise CartError(error_messages['price_not_a_number'])
                try:
                    custom_price = forms.DecimalField(localize=True).to_python(custom_price)
                except:
                    try:
                        custom_price = Decimal(custom_price)
                    except:
                        raise CartError(error_messages['price_not_a_number'])
                if custom_price > 99_999_999_999:
                    raise CartError(error_messages['price_too_high'])

            # Fix positions with wrong price (TODO: happens out-of-cartmanager-transaction and therefore a little hacky)
            for ca in current_addons[cp][a['item'], a['variation']]:
                if ca.listed_price != listed_price:
                    ca.listed_price = ca.listed_price
                    ca.price_after_voucher = ca.price_after_voucher
                    ca.save(update_fields=['listed_price', 'price_after_voucher'])
                if ca.custom_price_input != custom_price:
                    ca.custom_price_input = custom_price
                    ca.custom_price_input_is_net = self.event.settings.display_net_prices
                    ca.price_after_voucher = ca.price_after_voucher
                    ca.save(update_fields=['custom_price_input', 'custom_price_input'])

            if a.get('count', 1) > len(current_addons[cp][a['item'], a['variation']]):
                # This add-on is new, add it to the cart
                for quota in quotas:
                    quota_diff[quota] += a.get('count', 1) - len(current_addons[cp][a['item'], a['variation']])

                op = self.AddOperation(
                    count=a.get('count', 1) - len(current_addons[cp][a['item'], a['variation']]),
                    item=item,
                    variation=variation,
                    voucher=None,
                    quotas=quotas,
                    addon_to=cp,
                    subevent=cp.subevent,
                    bundled=[],
                    seat=None,
                    listed_price=listed_price,
                    price_after_voucher=listed_price,
                    custom_price_input=custom_price,
                    custom_price_input_is_net=self.event.settings.display_net_prices,
                    voucher_ignored=False,
                )
                self._check_item_constraints(op, operations)
                operations.append(op)

        # Check constraints on the add-on combinations
        for cp in toplevel_cp:
            item = cp.item
            for iao in item.addons.all():
                selected = selected_addons[cp.id, iao.addon_category_id]
                n_per_i = Counter()
                for (i, v), c in selected.items():
                    n_per_i[i] += c
                if sum(selected.values()) > iao.max_count:
                    raise CartError(
                        error_messages['addon_max_count'] % {
                            'base': str(item.name),
                            'max': iao.max_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )
                elif sum(selected.values()) < iao.min_count:
                    raise CartError(
                        error_messages['addon_min_count'] % {
                            'base': str(item.name),
                            'min': iao.min_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )
                elif any(v > 1 for v in n_per_i.values()) and not iao.multi_allowed:
                    raise CartError(
                        error_messages['addon_no_multi'] % {
                            'base': str(item.name),
                            'cat': str(iao.addon_category.name),
                        }
                    )
                validate_cart_addons.send(
                    sender=self.event,
                    addons={
                        (self._items_cache[s[0]], self._variations_cache[s[1]] if s[1] else None): c
                        for s, c in selected.items() if c > 0
                    },
                    base_position=cp,
                    iao=iao
                )

        # Detect removed add-ons and create RemoveOperations
        for cp, al in list(current_addons.items()):
            for k, v in al.items():
                input_num = input_addons[cp.id].get(k, 0)
                current_num = len(current_addons[cp].get(k, []))
                if input_num < current_num:
                    for a in current_addons[cp][k][:current_num - input_num]:
                        if a.expires > self.now_dt:
                            quotas = list(a.quotas)

                            for quota in quotas:
                                quota_diff[quota] -= 1

                        op = self.RemoveOperation(position=a)
                        operations.append(op)

        self._quota_diff.update(quota_diff)
        self._operations += operations

    def _get_voucher_availability(self):
        vouchers_ok, self._voucher_depend_on_cart = _get_voucher_availability(
            self.event, self._voucher_use_diff, self.now_dt,
            exclude_position_ids=[
                op.position.id for op in self._operations if isinstance(op, self.ExtendOperation)
            ]
        )
        return vouchers_ok

    def _check_min_max_per_product(self):
        items = Counter()
        for p in self.positions:
            items[p.item] += 1
        for op in self._operations:
            if isinstance(op, self.AddOperation):
                items[op.item] += op.count
                for bo in op.bundled:
                    items[bo.item] += bo.count
            elif isinstance(op, self.RemoveOperation):
                items[op.position.item] -= 1
                for a in op.position.addons.all():
                    items[a.item] -= 1

        err = None
        for item, count in items.items():
            if count == 0:
                continue

            if item.max_per_order and count > item.max_per_order:
                raise CartError(
                    error_messages['max_items_per_product'] % {
                        'max': item.max_per_order,
                        'product': item.name
                    }
                )

            if item.min_per_order and count < item.min_per_order:
                self._operations = [o for o in self._operations if not (
                    isinstance(o, self.AddOperation) and o.item.pk == item.pk
                )]
                removals = [o.position.pk for o in self._operations if isinstance(o, self.RemoveOperation)]
                for p in self.positions:
                    if p.item_id == item.pk and p.pk not in removals:
                        self._operations.append(self.RemoveOperation(position=p))
                        err = error_messages['min_items_per_product_removed'] % {
                            'min': item.min_per_order,
                            'product': item.name
                        }
                if not err:
                    raise CartError(
                        error_messages['min_items_per_product'] % {
                            'min': item.min_per_order,
                            'product': item.name
                        }
                    )
        return err

    def _check_min_per_voucher(self):
        vouchers = Counter()
        for p in self.positions:
            vouchers[p.voucher] += 1
        for op in self._operations:
            if isinstance(op, self.AddOperation):
                vouchers[op.voucher] += op.count
            elif isinstance(op, self.RemoveOperation):
                vouchers[op.position.voucher] -= 1

        err = None
        for voucher, count in vouchers.items():
            if not voucher or count == 0:
                continue
            if count < voucher.min_usages_remaining:
                self._operations = [o for o in self._operations if not (
                    isinstance(o, self.AddOperation) and o.voucher and o.voucher.pk == voucher.pk
                )]
                removals = [o.position.pk for o in self._operations if isinstance(o, self.RemoveOperation)]
                for p in self.positions:
                    if p.voucher_id == voucher.pk and p.pk not in removals:
                        self._operations.append(self.RemoveOperation(position=p))
                        err = error_messages['voucher_min_usages_removed'] % {
                            'voucher': voucher.code,
                            'number': voucher.min_usages_remaining,
                        }
                if not err:
                    raise CartError(
                        error_messages['voucher_min_usages'] % {
                            'voucher': voucher.code,
                            'number': voucher.min_usages_remaining,
                        }
                    )
        return err

    def _perform_operations(self):
        vouchers_ok = self._get_voucher_availability()
        quotas_ok = _get_quota_availability(self._quota_diff, self.now_dt)
        err = None
        new_cart_positions = []

        err = err or self._check_min_max_per_product()

        self._operations.sort(key=lambda a: self.order[type(a)])
        seats_seen = set()

        for iop, op in enumerate(self._operations):
            if isinstance(op, self.RemoveOperation):
                if op.position.expires > self.now_dt:
                    for q in op.position.quotas:
                        quotas_ok[q] += 1
                op.position.addons.all().delete()
                op.position.delete()

            elif isinstance(op, (self.AddOperation, self.ExtendOperation)):
                # Create a CartPosition for as much items as we can
                requested_count = quota_available_count = voucher_available_count = op.count

                if op.seat:
                    if op.seat in seats_seen:
                        err = err or error_messages['seat_multiple']
                    seats_seen.add(op.seat)

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
                        err = err or (error_messages['voucher_redeemed_cart'] % self.event.settings.reservation_time)
                    else:
                        err = err or error_messages['voucher_redeemed']
                elif voucher_available_count < requested_count:
                    err = err or (error_messages['voucher_redeemed_partial'] % voucher_available_count)

                available_count = min(quota_available_count, voucher_available_count)

                if isinstance(op, self.AddOperation):
                    for b in op.bundled:
                        b_quotas = list(b.quotas)
                        if not b_quotas:
                            if not op.voucher or not op.voucher.allow_ignore_quota:
                                err = err or error_messages['unavailable']
                                available_count = 0
                            continue
                        b_quota_available_count = min(available_count * b.count, min(quotas_ok[q] for q in b_quotas))
                        if b_quota_available_count < b.count:
                            err = err or error_messages['unavailable']
                            available_count = 0
                        elif b_quota_available_count < available_count * b.count:
                            err = err or error_messages['in_part']
                            available_count = b_quota_available_count // b.count
                        for q in b_quotas:
                            quotas_ok[q] -= available_count * b.count
                            # TODO: is this correct?

                for q in op.quotas:
                    quotas_ok[q] -= available_count
                if op.voucher:
                    vouchers_ok[op.voucher] -= available_count

                if any(qa < 0 for qa in quotas_ok.values()):
                    # Safeguard, shouldn't happen
                    err = err or error_messages['unavailable']
                    available_count = 0

                if isinstance(op, self.AddOperation):
                    if op.seat and not op.seat.is_available(ignore_voucher_id=op.voucher.id if op.voucher else None,
                                                            sales_channel=self._sales_channel,
                                                            distance_ignore_cart_id=self.cart_id):
                        available_count = 0
                        err = err or error_messages['seat_unavailable']

                    for k in range(available_count):
                        line_price = get_line_price(
                            price_after_voucher=op.price_after_voucher,
                            custom_price_input=op.custom_price_input,
                            custom_price_input_is_net=op.custom_price_input_is_net,
                            tax_rule=op.item.tax_rule,
                            invoice_address=self.invoice_address,
                            bundled_sum=sum([pp.count * pp.price_after_voucher for pp in op.bundled]),
                        )
                        cp = CartPosition(
                            event=self.event,
                            item=op.item,
                            variation=op.variation,
                            expires=self._expiry,
                            cart_id=self.cart_id,
                            voucher=op.voucher,
                            addon_to=op.addon_to if op.addon_to else None,
                            subevent=op.subevent,
                            seat=op.seat,
                            listed_price=op.listed_price,
                            price_after_voucher=op.price_after_voucher,
                            custom_price_input=op.custom_price_input,
                            custom_price_input_is_net=op.custom_price_input_is_net,
                            line_price_gross=line_price.gross,
                            tax_rate=line_price.rate,
                            price=line_price.gross,
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

                        if op.bundled:
                            cp.save()  # Needs to be in the database already so we have a PK that we can reference
                            for b in op.bundled:
                                bline_price = (
                                    b.item.tax_rule or TaxRule(rate=Decimal('0.00'))
                                ).tax(b.listed_price, base_price_is='gross', invoice_address=self.invoice_address)  # todo compare with previous behaviour
                                for j in range(b.count):
                                    new_cart_positions.append(CartPosition(
                                        event=self.event,
                                        item=b.item,
                                        variation=b.variation,
                                        expires=self._expiry, cart_id=self.cart_id,
                                        voucher=None,
                                        addon_to=cp,
                                        subevent=b.subevent,
                                        listed_price=b.listed_price,
                                        price_after_voucher=b.price_after_voucher,
                                        custom_price_input=b.custom_price_input,
                                        custom_price_input_is_net=b.custom_price_input_is_net,
                                        line_price_gross=bline_price.gross,
                                        tax_rate=bline_price.rate,
                                        price=bline_price.gross,
                                        is_bundled=True
                                    ))

                        new_cart_positions.append(cp)
                elif isinstance(op, self.ExtendOperation):
                    if op.seat and not op.seat.is_available(ignore_cart=op.position, sales_channel=self._sales_channel,
                                                            ignore_voucher_id=op.position.voucher_id):
                        err = err or error_messages['seat_unavailable']
                        op.position.addons.all().delete()
                        op.position.delete()
                    elif available_count == 1:
                        op.position.expires = self._expiry
                        op.position.listed_price = op.listed_price
                        op.position.price_after_voucher = op.price_after_voucher
                        # op.position.price will be updated by recompute_final_prices_and_taxes()
                        try:
                            op.position.save(force_update=True, update_fields=['expires', 'listed_price', 'price_after_voucher'])
                        except DatabaseError:
                            # Best effort... The position might have been deleted in the meantime!
                            pass
                    elif available_count == 0:
                        op.position.addons.all().delete()
                        op.position.delete()
                    else:
                        raise AssertionError("ExtendOperation cannot affect more than one item")
            elif isinstance(op, self.VoucherOperation):
                if vouchers_ok[op.voucher] < 1:
                    if iop == 0:
                        raise CartError(error_messages['voucher_redeemed'])
                    else:
                        # We fail silently if we could only apply the voucher to part of the cart, since that might
                        # be expected
                        continue

                op.position.price_after_voucher = op.price_after_voucher
                op.position.voucher = op.voucher
                # op.posiiton.price will be set in recompute_final_prices_and_taxes
                op.position.save(update_fields=['price_after_voucher', 'voucher'])
                vouchers_ok[op.voucher] -= 1

        for p in new_cart_positions:
            if getattr(p, '_answers', None):
                if not p.pk:  # We stored some to the database already before
                    p.save()
                _save_answers(p, {}, p._answers)
        CartPosition.objects.bulk_create([p for p in new_cart_positions if not getattr(p, '_answers', None) and not p.pk])
        return err

    def _require_locking(self):
        if self._voucher_use_diff:
            # If any vouchers are used, we lock to make sure we don't redeem them to often
            return True

        if self._quota_diff and any(q.size is not None for q in self._quota_diff):
            # If any quotas are affected that are not unlimited, we lock
            return True

        if any(getattr(o, 'seat', False) for o in self._operations):
            return True

        return False

    def recompute_final_prices_and_taxes(self):
        positions = sorted(list(self.positions), key=lambda op: -(op.addon_to_id or 0))
        diff = Decimal('0.00')
        for cp in positions:
            if cp.listed_price is None:
                # migration from old system? also used in unit tests
                cp.update_listed_price_and_voucher()
                cp.migrate_free_price_if_necessary()

            cp.update_line_price(self.invoice_address, [b for b in positions if b.addon_to_id == cp.pk and b.is_bundled])

        discount_results = apply_discounts(
            self.event,
            self._sales_channel,
            [
                (cp.item_id, cp.subevent_id, cp.line_price_gross, bool(cp.addon_to), cp.is_bundled, cp.listed_price - cp.price_after_voucher)
                for cp in positions
            ]
        )

        for cp, (new_price, discount) in zip(positions, discount_results):
            if cp.price != new_price or cp.discount_id != (discount.pk if discount else None):
                diff += new_price - cp.price
                cp.price = new_price
                cp.discount = discount
                cp.save(update_fields=['price', 'discount'])

        return diff

    def commit(self):
        self._check_presale_dates()
        self._check_max_cart_size()
        self._calculate_expiry()

        err = self._delete_out_of_timeframe()
        err = self.extend_expired_positions() or err
        err = err or self._check_min_per_voucher()

        lockfn = NoLockManager
        if self._require_locking():
            lockfn = self.event.lock

        with lockfn() as now_dt:
            with transaction.atomic():
                self.now_dt = now_dt
                self._extend_expiry_of_valid_existing_positions()
                err = self._perform_operations() or err
                self.recompute_final_prices_and_taxes()
            if err:
                raise CartError(err)


def add_payment_to_cart(request, provider, min_value: Decimal=None, max_value: Decimal=None, info_data: dict=None):
    """
    :param request: The current HTTP request context.
    :param provider: The instance of your payment provider.
    :param min_value: The minimum value this payment instrument supports, or ``None`` for unlimited.
    :param max_value: The maximum value this payment instrument supports, or ``None`` for unlimited. Highly discouraged
                      to use for payment providers which charge a payment fee, as this can be very user-unfriendly if
                      users need a second payment method just for the payment fee of the first method.
    :param info_data: A dictionary of information that will be passed through to the ``OrderPayment.info_data`` attribute.
    :return:
    """
    from pretix.presale.views.cart import cart_session

    cs = cart_session(request)
    cs.setdefault('payments', [])

    cs['payments'].append({
        'id': str(uuid.uuid4()),
        'provider': provider.identifier,
        'multi_use_supported': provider.multi_use_supported,
        'min_value': str(min_value) if min_value is not None else None,
        'max_value': str(max_value) if max_value is not None else None,
        'info_data': info_data or {},
    })


def get_fees(event, request, total, invoice_address, payments, positions):
    if payments and not isinstance(payments, list):
        raise TypeError("payments must now be a list")

    fees = []
    for recv, resp in fee_calculation_for_cart.send(sender=event, request=request, invoice_address=invoice_address,
                                                    total=total, positions=positions, payment_requests=payments):
        if resp:
            fees += resp

    total = total + sum(f.value for f in fees)

    if total != 0 and payments:
        total_remaining = total
        for p in payments:
            # This algorithm of treating min/max values and fees needs to stay in sync between the following
            # places in the code base:
            # - pretix.base.services.cart.get_fees
            # - pretix.base.services.orders._get_fees
            # - pretix.presale.views.CartMixin.current_selected_payments
            if p.get('min_value') and total_remaining < Decimal(p['min_value']):
                continue

            to_pay = total_remaining
            if p.get('max_value') and to_pay > Decimal(p['max_value']):
                to_pay = min(to_pay, Decimal(p['max_value']))

            pprov = event.get_payment_providers(cached=True).get(p['provider'])
            if not pprov:
                continue

            payment_fee = pprov.calculate_fee(to_pay)
            total_remaining += payment_fee
            to_pay += payment_fee

            if p.get('max_value') and to_pay > Decimal(p['max_value']):
                to_pay = min(to_pay, Decimal(p['max_value']))

            total_remaining -= to_pay

            if payment_fee:
                payment_fee_tax_rule = event.settings.tax_rate_default or TaxRule.zero()
                payment_fee_tax = payment_fee_tax_rule.tax(payment_fee, base_price_is='gross', invoice_address=invoice_address)
                fees.append(OrderFee(
                    fee_type=OrderFee.FEE_TYPE_PAYMENT,
                    value=payment_fee,
                    tax_rate=payment_fee_tax.rate,
                    tax_value=payment_fee_tax.tax,
                    tax_rule=payment_fee_tax_rule
                ))

    return fees


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def add_items_to_cart(self, event: int, items: List[dict], cart_id: str=None, locale='en',
                      invoice_address: int=None, widget_data=None, sales_channel='web') -> None:
    """
    Adds a list of items to a user's cart.
    :param event: The event ID in question
    :param items: A list of dicts with the keys item, variation, count, custom_price, voucher, seat ID
    :param cart_id: Session ID of a guest
    :raises CartError: On any error that occurred
    """
    with language(locale):
        ia = False
        if invoice_address:
            try:
                with scopes_disabled():
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


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def apply_voucher(self, event: Event, voucher: str, cart_id: str=None, locale='en', sales_channel='web') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param voucher: A voucher code
    :param session: Session ID of a guest
    """
    with language(locale):
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, sales_channel=sales_channel)
                cm.apply_voucher(voucher)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def remove_cart_position(self, event: Event, position: int, cart_id: str=None, locale='en', sales_channel='web') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param position: A cart position ID
    :param session: Session ID of a guest
    """
    with language(locale):
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, sales_channel=sales_channel)
                cm.remove_item(position)
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def clear_cart(self, event: Event, cart_id: str=None, locale='en', sales_channel='web') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param session: Session ID of a guest
    """
    with language(locale):
        try:
            try:
                cm = CartManager(event=event, cart_id=cart_id, sales_channel=sales_channel)
                cm.clear()
                cm.commit()
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise CartError(error_messages['busy'])


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(CartError,))
def set_cart_addons(self, event: Event, addons: List[dict], cart_id: str=None, locale='en',
                    invoice_address: int=None, sales_channel='web') -> None:
    """
    Removes a list of items from a user's cart.
    :param event: The event ID in question
    :param addons: A list of dicts with the keys addon_to, item, variation
    :param session: Session ID of a guest
    """
    with language(locale):
        ia = False
        if invoice_address:
            try:
                with scopes_disabled():
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
    if not sender.settings.confirm_texts:
        return {}
    confirm_texts = sender.settings.get("confirm_texts", as_type=LazyI18nStringList)
    return {'confirm_text_%i' % index: rich_text(str(text)) for index, text in enumerate(confirm_texts)}
