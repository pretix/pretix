from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_scopes import ScopedManager, scopes_disabled

from pretix.base.banlist import banned
from pretix.base.models import Seat, SeatCategoryMapping

from ..decimal import round_decimal
from .base import LoggedModel
from .event import Event, SubEvent
from .items import Item, ItemVariation, Quota
from .orders import Order, OrderPosition


def _generate_random_code(prefix=None):
    charset = list('ABCDEFGHKLMNPQRSTUVWXYZ23456789')
    rnd = None
    while not rnd or banned(rnd):
        rnd = get_random_string(length=settings.ENTROPY['voucher_code'], allowed_chars=charset)
    if prefix:
        return prefix + rnd
    return rnd


@scopes_disabled()
def generate_code(prefix=None):
    while True:
        code = _generate_random_code(prefix=prefix)
        if not Voucher.objects.filter(code__iexact=code).exists():
            return code


class Voucher(LoggedModel):
    """
    A Voucher can reserve ticket quota or allow special prices.

    :param event: The event this voucher is valid for
    :type event: Event
    :param subevent: The date in the event series, if event series are enabled
    :type subevent: SubEvent
    :param code: The secret voucher code
    :type code: str
    :param max_usages: The number of times this voucher can be redeemed
    :type max_usages: int
    :param redeemed: The number of times this voucher already has been redeemed
    :type redeemed: int
    :param valid_until: The expiration date of this voucher (optional)
    :type valid_until: datetime
    :param block_quota: If set to true, this voucher will reserve quota for its holder
    :type block_quota: bool
    :param allow_ignore_quota: If set to true, this voucher can be redeemed even if the event is sold out
    :type allow_ignore_quota: bool
    :param price_mode: Sets how this voucher affects a product's price. Can be ``none``, ``set``, ``subtract``
                       or ``percent``.
    :type price_mode: str
    :param value: The value by which the price should be modified in the way specified by ``price_mode``.
    :type value: decimal.Decimal
    :param item: If set, the item to sell
    :type item: Item
    :param variation: If set, the variation to sell
    :type variation: ItemVariation
    :param quota: If set, the quota to choose an item from
    :type quota: Quota
    :param comment: An internal comment that will only be visible to staff, and never displayed to the user
    :type comment: str
    :param tag: Use this field to group multiple vouchers together. If you enter the same value for multiple
                vouchers, you can get statistics on how many of them have been redeemed etc.
    :type tag: str

    Various constraints apply:

    * You need to either select a quota or an item
    * If you select an item that has variations but do not select a variation, you cannot set block_quota
    """
    PRICE_MODES = (
        ('none', _('No effect')),
        ('set', _('Set product price to')),
        ('subtract', _('Subtract from product price')),
        ('percent', _('Reduce product price by (%)')),
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="vouchers",
        verbose_name=_("Event"),
    )
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.CASCADE,
        verbose_name=pgettext_lazy("subevent", "Date"),
    )
    code = models.CharField(
        verbose_name=_("Voucher code"),
        max_length=255, default=generate_code,
        db_index=True,
        validators=[MinLengthValidator(5)]
    )
    max_usages = models.PositiveIntegerField(
        verbose_name=_("Maximum usages"),
        help_text=_("Number of times this voucher can be redeemed."),
        default=1
    )
    redeemed = models.PositiveIntegerField(
        verbose_name=_("Redeemed"),
        default=0
    )
    budget = models.DecimalField(
        verbose_name=_("Maximum discount budget"),
        help_text=_("This is the maximum monetary amount that will be discounted using this voucher. If this is reached, "
                    "the voucher becomes inactive."),
        decimal_places=2, max_digits=10,
        null=True, blank=True
    )
    valid_until = models.DateTimeField(
        blank=True, null=True, db_index=True,
        verbose_name=_("Valid until")
    )
    block_quota = models.BooleanField(
        default=False,
        verbose_name=_("Reserve ticket from quota"),
        help_text=_(
            "If activated, this voucher will be substracted from the affected product\'s quotas, such that it is "
            "guaranteed that anyone with this voucher code does receive a ticket."
        )
    )
    allow_ignore_quota = models.BooleanField(
        default=False,
        verbose_name=_("Allow to bypass quota"),
        help_text=_(
            "If activated, a holder of this voucher code can buy tickets, even if there are none left."
        )
    )
    price_mode = models.CharField(
        verbose_name=_("Price mode"),
        max_length=100,
        choices=PRICE_MODES,
        default='none'
    )
    value = models.DecimalField(
        verbose_name=_("Voucher value"),
        decimal_places=2, max_digits=10, null=True, blank=True,
    )
    item = models.ForeignKey(
        Item, related_name='vouchers',
        verbose_name=_("Product"),
        null=True, blank=True,
        on_delete=models.PROTECT,  # We use a fake version of SET_NULL in Item.delete()
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed."
        )
    )
    variation = models.ForeignKey(
        ItemVariation, related_name='vouchers',
        null=True, blank=True,
        on_delete=models.PROTECT,  # We use a fake version of SET_NULL in ItemVariation.delete() to avoid the semantic change
                                   # that would happen if we just set variation to None
        verbose_name=_("Product variation"),
        help_text=_(
            "This variation of the product select above is being used."
        )
    )
    quota = models.ForeignKey(
        Quota, related_name='vouchers',
        null=True, blank=True,
        on_delete=models.PROTECT,  # We use a fake version of SET_NULL in Quota.delete()
        verbose_name=_("Quota"),
        help_text=_(
            "If enabled, the voucher is valid for any product affected by this quota."
        )
    )
    seat = models.ForeignKey(
        Seat, related_name='vouchers',
        null=True, blank=True,
        on_delete=models.PROTECT,
        verbose_name=_("Specific seat"),
    )
    tag = models.CharField(
        max_length=255,
        verbose_name=_("Tag"),
        blank=True,
        db_index=True,
        help_text=_("You can use this field to group multiple vouchers together. If you enter the same value for "
                    "multiple vouchers, you can get statistics on how many of them have been redeemed etc.")
    )
    comment = models.TextField(
        blank=True, verbose_name=_("Comment"),
        help_text=_("The text entered in this field will not be visible to the user and is available for your "
                    "convenience.")
    )
    show_hidden_items = models.BooleanField(
        verbose_name=_("Shows hidden products that match this voucher"),
        default=True
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Voucher")
        verbose_name_plural = _("Vouchers")
        unique_together = (("event", "code"),)
        ordering = ('code', )

    def __str__(self):
        return self.code

    def allow_delete(self):
        return self.redeemed == 0 and not self.orderposition_set.exists()

    def clean(self):
        Voucher.clean_item_properties(
            {
                'block_quota': self.block_quota,
            },
            self.event,
            self.quota,
            self.item,
            self.variation,
            seats_given=bool(self.seat)
        )

    @staticmethod
    def clean_item_properties(data, event, quota, item, variation, block_quota=False, seats_given=False):
        if quota:
            if quota.event != event:
                raise ValidationError(_('You cannot select a quota that belongs to a different event.'))
            if item:
                raise ValidationError(_('You cannot select a quota and a specific product at the same time.'))
        elif item:
            if item.event != event:
                raise ValidationError(_('You cannot select an item that belongs to a different event.'))
            if variation and (not item or not item.has_variations):
                raise ValidationError(_('You cannot select a variation without having selected a product that provides '
                                        'variations.'))
            if variation and not item.variations.filter(pk=variation.pk).exists():
                raise ValidationError(_('This variation does not belong to this product.'))
            if item.has_variations and not variation and data.get('block_quota'):
                raise ValidationError(_('You can only block quota if you specify a specific product variation. '
                                        'Otherwise it might be unclear which quotas to block.'))
            if item.category and item.category.is_addon:
                raise ValidationError(_('It is currently not possible to create vouchers for add-on products.'))
        elif block_quota:
            raise ValidationError(_('You need to select a specific product or quota if this voucher should reserve '
                                    'tickets.'))
        elif variation:
            raise ValidationError(_('You cannot select a variation without having selected a product that provides '
                                    'variations.'))

    @staticmethod
    def clean_max_usages(data, redeemed):
        if data.get('max_usages', 1) < redeemed:
            raise ValidationError(
                _('This voucher has already been redeemed %(redeemed)s times. You cannot reduce the maximum number of '
                  'usages below this number.'),
                params={
                    'redeemed': redeemed
                }
            )

    @staticmethod
    def clean_subevent(data, event):
        if event.has_subevents and data.get('block_quota') and not data.get('subevent'):
            raise ValidationError(_('If you want this voucher to block quota, you need to select a specific date.'))
        elif data.get('subevent') and not event.has_subevents:
            raise ValidationError(_('You can not select a subevent if your event is not an event series.'))

    @staticmethod
    def clean_quota_needs_checking(data, old_instance, item_changed, creating):
        # We only need to check for quota on vouchers that are now blocking quota and haven't
        # before (or have blocked a different quota before)
        if data.get('allow_ignore_quota', False):
            return False
        if data.get('block_quota', False):
            is_valid = data.get('valid_until') is None or data.get('valid_until') >= now()
            if not is_valid:
                # If the voucher is not valid, it won't block any quota
                return False

            if creating:
                # This is a new voucher
                return True

            if not old_instance.block_quota:
                # Change from nonblocking to blocking
                return True

            if old_instance.valid_until is not None and old_instance.valid_until < now():
                # This voucher has been expired and is now valid again and therefore blocks quota again
                return True

            if item_changed:
                # The voucher has been reassigned to a different item, variation or quota
                return True

            if data.get('subevent') != old_instance.subevent:
                # The voucher has been reassigned to a different subevent
                return True

        return False

    @staticmethod
    def clean_quota_get_ignored(old_instance):
        quotas = set()
        was_valid = old_instance and (
            old_instance.valid_until is None or old_instance.valid_until >= now()
        )
        if old_instance and old_instance.block_quota and was_valid:
            if old_instance.quota:
                quotas.add(old_instance.quota)
            elif old_instance.variation:
                quotas |= set(old_instance.variation.quotas.filter(subevent=old_instance.subevent))
            elif old_instance.item:
                quotas |= set(old_instance.item.quotas.filter(subevent=old_instance.subevent))
        return quotas

    @staticmethod
    def clean_quota_check(data, cnt, old_instance, event, quota, item, variation):
        old_quotas = Voucher.clean_quota_get_ignored(old_instance)

        if event.has_subevents and data.get('block_quota') and not data.get('subevent'):
            raise ValidationError(_('If you want this voucher to block quota, you need to select a specific date.'))

        if quota:
            if quota in old_quotas:
                return
            else:
                avail = quota.availability(count_waitinglist=False)
        elif item and item.has_variations and not variation:
            raise ValidationError(_('You can only block quota if you specify a specific product variation. '
                                    'Otherwise it might be unclear which quotas to block.'))
        elif item and variation:
            avail = variation.check_quotas(ignored_quotas=old_quotas, subevent=data.get('subevent'))
        elif item and not item.has_variations:
            avail = item.check_quotas(ignored_quotas=old_quotas, subevent=data.get('subevent'))
        else:
            raise ValidationError(_('You need to select a specific product or quota if this voucher should reserve '
                                    'tickets.'))

        if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < cnt):
            raise ValidationError(_('You cannot create a voucher that blocks quota as the selected product or '
                                    'quota is currently sold out or completely reserved.'))

    @staticmethod
    def clean_voucher_code(data, event, pk):
        if 'code' in data and Voucher.objects.filter(Q(code__iexact=data['code']) & Q(event=event) & ~Q(pk=pk)).exists():
            raise ValidationError(_('A voucher with this code already exists.'))

    @staticmethod
    def clean_seat_id(data, item, quota, event, pk):
        try:
            if event.has_subevents:
                if not data.get('subevent'):
                    raise ValidationError(_('You need to choose a date if you select a seat.'))
                seat = event.seats.select_related('product').get(
                    seat_guid=data.get('seat'), subevent=data.get('subevent')
                )
            else:
                seat = event.seats.select_related('product').get(
                    seat_guid=data.get('seat')
                )
        except Seat.DoesNotExist:
            raise ValidationError(_('The specified seat ID "{id}" does not exist for this event.').format(
                id=data.get('seat')))

        if not seat.is_available(ignore_voucher_id=pk, ignore_cart=True):
            raise ValidationError(_('The seat "{id}" is currently unavailable (blocked, already sold or a '
                                    'different voucher).').format(
                id=seat.seat_guid))

        if quota:
            raise ValidationError(_('You need to choose a specific product if you select a seat.'))

        if data.get('max_usages', 1) > 1:
            raise ValidationError(_('Seat-specific vouchers can only be used once.'))

        if item and seat.product != item:
            raise ValidationError(_('You need to choose the product "{prod}" for this seat.').format(prod=seat.product))

        if not seat.is_available(ignore_voucher_id=pk):
            raise ValidationError(_('The seat "{id}" is already sold or currently blocked.').format(id=seat.seat_guid))

        return seat

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)
        self.event.cache.set('vouchers_exist', True)

    def delete(self, using=None, keep_parents=False):
        super().delete(using, keep_parents)
        self.event.cache.delete('vouchers_exist')

    def is_in_cart(self) -> bool:
        """
        Returns whether a cart position exists that uses this voucher.
        """
        return self.cartposition_set.exists()

    def is_ordered(self) -> bool:
        """
        Returns whether an order position exists that uses this voucher.
        """
        return self.orderposition_set.exists()

    def applies_to(self, item: Item, variation: ItemVariation=None) -> bool:
        """
        Returns whether this voucher applies to a given item (and optionally
        a variation).
        """
        if self.quota_id:
            if variation:
                return variation.quotas.filter(pk=self.quota_id).exists()
            return item.quotas.filter(pk=self.quota_id).exists()
        if self.item_id and not self.variation_id:
            return self.item_id == item.pk
        if self.item_id:
            return (self.item_id == item.pk) and (variation and self.variation_id == variation.pk)
        return True

    def is_active(self):
        """
        Returns True if a voucher has not yet been redeemed, but is still
        within its validity (if valid_until is set).
        """
        if self.redeemed >= self.max_usages:
            return False
        if self.valid_until and self.valid_until < now():
            return False
        return True

    def calculate_price(self, original_price: Decimal, max_discount: Decimal=None) -> Decimal:
        """
        Returns how the price given in original_price would be modified if this
        voucher is applied, i.e. replaced by a different price or reduced by a
        certain percentage. If the voucher does not modify the price, the
        original price will be returned.
        """
        if self.value is not None:
            if self.price_mode == 'set':
                p = self.value
            elif self.price_mode == 'subtract':
                p = max(original_price - self.value, Decimal('0.00'))
            elif self.price_mode == 'percent':
                p = round_decimal(original_price * (Decimal('100.00') - self.value) / Decimal('100.00'))
            else:
                p = original_price
            places = settings.CURRENCY_PLACES.get(self.event.currency, 2)
            if places < 2:
                p = p.quantize(Decimal('1') / 10 ** places, ROUND_HALF_UP)
            if max_discount is not None:
                p = max(p, original_price - max_discount)
            return p
        return original_price

    def distinct_orders(self):
        """
        Return the list of orders where this voucher has been used.
        Each order will appear at most once.
        """

        return Order.objects.filter(all_positions__voucher__in=[self]).distinct()

    def seating_available(self, subevent):
        kwargs = {}
        if self.subevent:
            kwargs['subevent'] = self.subevent
        if self.quota_id:
            return SeatCategoryMapping.objects.filter(product__quotas__pk=self.quota_id, **kwargs).exists()
        elif self.item_id:
            return self.item.seat_category_mappings.filter(**kwargs).exists()
        else:
            return bool(subevent.seating_plan) if subevent else self.event.seating_plan

    @classmethod
    def annotate_budget_used_orders(cls, qs):
        opq = OrderPosition.objects.filter(
            voucher_id=OuterRef('pk'),
            price_before_voucher__isnull=False,
            order__status__in=[
                Order.STATUS_PAID,
                Order.STATUS_PENDING
                # TODO: reason about expired orders
            ]
        ).order_by().values('voucher_id').annotate(s=Sum(F('price_before_voucher') - F('price'))).values('s')
        return qs.annotate(budget_used_orders=Coalesce(Subquery(opq, output_field=models.DecimalField(max_digits=10, decimal_places=2)), Decimal('0.00')))

    def budget_used(self):
        ops = OrderPosition.objects.filter(
            voucher=self,
            price_before_voucher__isnull=False,
            order__status__in=[
                Order.STATUS_PAID,
                Order.STATUS_PENDING
                # TODO: reason about expired orders
            ]
        ).aggregate(s=Sum(F('price_before_voucher') - F('price')))['s'] or Decimal('0.00')
        return ops
