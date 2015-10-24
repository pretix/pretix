from django.db import models
from django.utils.translation import ugettext_lazy as _

from .event import Event
from .items import Item
from .orders import CartPosition, OrderPosition


class Voucher(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="vouchers",
        verbose_name=_("Event"),
    )
    code = models.CharField(
        verbose_name=_("Voucher code"),
        max_length=255
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
        decimal_places=2, max_digits=10, null=True, blank=True
    )
    item = models.ManyToManyField(
        Item, related_name='vouchers',
        verbose_name=_("Product"),
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed."
        )
    )

    class Meta:
        verbose_name = _("Voucher")
        verbose_name_plural = _("Vouchers")
        unique_together = (("event", "code"),)

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    def is_ordered(self) -> int:
        return OrderPosition.objects.current.filter(
            voucher=self.voucher
        ).exists()

    def is_in_cart(self) -> int:
        return CartPosition.objects.current.filter(
            voucher=self.voucher
        ).count()
