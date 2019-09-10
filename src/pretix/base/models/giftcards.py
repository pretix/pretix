from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.crypto import get_random_string


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


class GiftCard(models.Model):
    issuer = models.ForeignKey(
        'Organizer',
        related_name='issued_gift_cards',
        on_delete=models.PROTECT,
    )
    issued_in = models.ForeignKey(
        'OrderPosition',
        related_name='issued_gift_cards',
        on_delete=models.PROTECT,
    )
    issuance = models.DateTimeField(
        auto_now_add=True,
    )
    secret = models.CharField(
        max_length=190,
        default=gen_giftcard_secret,
        unique=True,
        db_index=True,
    )
    currency = models.CharField(max_length=10)

    @property
    def value(self):
        return self.transactions.aggregate(s=Sum('value'))['s'] or Decimal('0.00')


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
