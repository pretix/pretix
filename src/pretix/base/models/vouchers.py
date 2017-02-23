from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from ..decimal import round_decimal
from .base import LoggedModel
from .event import Event
from .items import Item, ItemVariation, Quota


def _generate_random_code():
    charset = list('ABCDEFGHKLMNPQRSTUVWXYZ23456789')
    return get_random_string(length=settings.ENTROPY['voucher_code'], allowed_chars=charset)


def generate_code():
    while True:
        code = _generate_random_code()
        if not Voucher.objects.filter(code=code).exists():
            return code


class Voucher(LoggedModel):
    """
    A Voucher can reserve ticket quota or allow special prices.

    :param event: The event this voucher is valid for
    :type event: Event
    :param code: The secret voucher code
    :type code: str
    :param max_usages: The number of times this voucher can be redeemed
    :type max_usages: int
    :param redeemed: The number of times this voucher already has been redeemed
    :type redeemed: bool
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
    code = models.CharField(
        verbose_name=_("Voucher code"),
        max_length=255, default=generate_code,
        db_index=True,
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
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed."
        )
    )
    variation = models.ForeignKey(
        ItemVariation, related_name='vouchers',
        null=True, blank=True,
        verbose_name=_("Product variation"),
        help_text=_(
            "This variation of the product select above is being used."
        )
    )
    quota = models.ForeignKey(
        Quota, related_name='quota',
        null=True, blank=True,
        verbose_name=_("Quota"),
        help_text=_(
            "If enabled, the voucher is valid for any product affected by this quota."
        )
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

    class Meta:
        verbose_name = _("Voucher")
        verbose_name_plural = _("Vouchers")
        unique_together = (("event", "code"),)

    def __str__(self):
        return self.code

    def clean(self):
        super().clean()
        if self.quota:
            if self.item:
                raise ValidationError(_('You cannot select a quota and a specific product at the same time.'))
        elif self.item:
            if self.variation and (not self.item or not self.item.has_variations):
                raise ValidationError(_('You cannot select a variation without having selected a product that provides '
                                        'variations.'))
            if self.variation and not self.item.variations.filter(pk=self.variation.pk).exists():
                raise ValidationError(_('This variation does not belong to this product.'))
            if self.item.has_variations and not self.variation and self.block_quota:
                raise ValidationError(_('You can only block quota if you specify a specific product variation. '
                                        'Otherwise it might be unclear which quotas to block.'))
        else:
            raise ValidationError(_('You need to specify either a quota or a product.'))

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)
        self.event.get_cache().set('vouchers_exist', True)

    def delete(self, using=None, keep_parents=False):
        super().delete(using, keep_parents)
        self.event.get_cache().delete('vouchers_exist')

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
            return item.quotas.filter(pk=self.quota_id).exists()
        if self.item_id and not self.variation_id:
            return self.item_id == item.pk
        return (self.item_id == item.pk) and (variation and self.variation_id == variation.pk)

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

    def calculate_price(self, original_price: Decimal) -> Decimal:
        """
        Returns how the price given in original_price would be modified if this
        voucher is applied, i.e. replaced by a different price or reduced by a
        certain percentage. If the voucher does not modify the price, the
        original price will be returned.
        """
        if self.value is not None:
            if self.price_mode == 'set':
                return self.value
            elif self.price_mode == 'subtract':
                return original_price - self.value
            elif self.price_mode == 'percent':
                return round_decimal(original_price * (Decimal('100.00') - self.value) / Decimal('100.00'))
        return original_price
