import random
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _

from .base import LoggedModel
from .event import Event
from .items import Item, ItemVariation, Quota
from .orders import CartPosition, OrderPosition


def generate_code():
    charset = list('ABCDEFGHKLMNPQRSTUVWXYZ23456789')
    while True:
        code = "".join([random.choice(charset) for i in range(16)])
        if not Voucher.objects.filter(code=code).exists():
            return code


class Voucher(LoggedModel):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="vouchers",
        verbose_name=_("Event"),
    )
    code = models.CharField(
        verbose_name=_("Voucher code"),
        max_length=255, default=generate_code
    )
    redeemed = models.BooleanField(
        verbose_name=_("Redeemed"),
        default=False
    )
    valid_until = models.DateTimeField(
        blank=True, null=True,
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
    price = models.DecimalField(
        verbose_name=_("Set product price to"),
        decimal_places=2, max_digits=10, null=True, blank=True,
        help_text=_('If empty, the product will cost its normal price.')
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

    def is_ordered(self) -> int:
        return OrderPosition.objects.filter(
            voucher=self
        ).exists()

    def is_in_cart(self) -> int:
        return CartPosition.objects.filter(
            voucher=self
        ).count()
