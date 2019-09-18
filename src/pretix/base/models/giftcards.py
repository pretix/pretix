from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import LoggedModel


def gen_giftcard_secret():
    charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
    while True:
        code = get_random_string(length=settings.ENTROPY['giftcard_secret'], allowed_chars=charset)
        if not GiftCard.objects.filter(secret=code).exists():
            return code


class GiftCardAcceptance(models.Model):
    issuer = models.ForeignKey(
        'Organizer',
        related_name='gift_card_collector_acceptance',
        on_delete=models.CASCADE
    )
    collector = models.ForeignKey(
        'Organizer',
        related_name='gift_card_issuer_acceptance',
        on_delete=models.CASCADE
    )


class GiftCard(LoggedModel):
    issuer = models.ForeignKey(
        'Organizer',
        related_name='issued_gift_cards',
        on_delete=models.PROTECT,
    )
    issued_in = models.ForeignKey(
        'OrderPosition',
        related_name='issued_gift_cards',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    issuance = models.DateTimeField(
        auto_now_add=True,
    )
    secret = models.CharField(
        max_length=190,
        default=gen_giftcard_secret,
        db_index=True,
        verbose_name=_('Gift card code'),
    )
    CURRENCY_CHOICES = [(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES]
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES)

    def __str__(self):
        return self.secret

    @property
    def value(self):
        return self.transactions.aggregate(s=Sum('value'))['s'] or Decimal('0.00')

    class Meta:
        unique_together = (('secret', 'issuer'),)


class GiftCardTransaction(models.Model):
    card = models.ForeignKey(
        'GiftCard',
        related_name='transactions',
        on_delete=models.PROTECT
    )
    datetime = models.DateTimeField(
        auto_now_add=True
    )
    value = models.DecimalField(
        decimal_places=2,
        max_digits=10
    )
    order = models.ForeignKey(
        'Order',
        related_name='gift_card_transactions',
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )
    payment = models.ForeignKey(
        'OrderPayment',
        related_name='gift_card_transactions',
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )
    refund = models.ForeignKey(
        'OrderRefund',
        related_name='gift_card_transactions',
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    class Meta:
        ordering = ("datetime",)
