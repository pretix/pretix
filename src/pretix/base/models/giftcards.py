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
from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Sum
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.banlist import banned
from pretix.base.models import LoggedModel


def gen_giftcard_secret(length=8):
    charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
    while True:
        code = get_random_string(length=length, allowed_chars=charset)
        if not banned(code) and not GiftCard.objects.filter(secret=code).exists():
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
        db_index=True,
        verbose_name=_('Gift card code'),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9][a-zA-Z0-9.-]+$",
                message=_("The gift card code may only contain letters, numbers, dots and dashes."),
            )
        ],
    )
    testmode = models.BooleanField(
        verbose_name=_('Test mode card'),
        default=False
    )
    expires = models.DateTimeField(
        null=True, blank=True, verbose_name=_('Expiry date')
    )
    conditions = models.TextField(
        null=True, blank=True, verbose_name=pgettext_lazy('giftcard', 'Special terms and conditions')
    )
    CURRENCY_CHOICES = [(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES]
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES)

    def __str__(self):
        return self.secret

    @property
    def expired(self):
        return self.expires and now() > self.expires

    @property
    def value(self):
        return self.transactions.aggregate(s=Sum('value'))['s'] or Decimal('0.00')

    def accepted_by(self, organizer):
        return self.issuer == organizer or GiftCardAcceptance.objects.filter(issuer=self.issuer, collector=organizer).exists()

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = gen_giftcard_secret(self.issuer.settings.giftcard_length)

        super().save(*args, **kwargs)

    class Meta:
        unique_together = (('secret', 'issuer'),)
        ordering = ("issuance",)


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
    text = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ("datetime",)
