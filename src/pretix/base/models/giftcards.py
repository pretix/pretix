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
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.html import format_html
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
        related_name='gift_card_acceptor_acceptance',
        on_delete=models.CASCADE
    )
    acceptor = models.ForeignKey(
        'Organizer',
        related_name='gift_card_issuer_acceptance',
        on_delete=models.CASCADE
    )
    active = models.BooleanField(default=True)
    reusable_media = models.BooleanField(default=False)

    class Meta:
        unique_together = (('issuer', 'acceptor'),)


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
    owner_ticket = models.ForeignKey(
        'OrderPosition',
        related_name='owned_gift_cards',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name=_('Owned by ticket holder')
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
        return self.issuer == organizer or GiftCardAcceptance.objects.filter(issuer=self.issuer, acceptor=organizer, active=True).exists()

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
        max_digits=13
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
    info = models.JSONField(
        null=True, blank=True,
    )
    acceptor = models.ForeignKey(
        'Organizer',
        related_name='gift_card_transactions',
        on_delete=models.PROTECT,
        null=True, blank=True
    )

    class Meta:
        ordering = ("datetime",)

    def save(self, *args, **kwargs):
        if not self.pk and not self.acceptor:
            raise ValueError("`acceptor` should be set on all new gift card transactions.")
        super().save(*args, **kwargs)

    def display(self, customer_facing=True):
        from ..signals import gift_card_transaction_display

        for receiver, response in gift_card_transaction_display.send(self, transaction=self, customer_facing=customer_facing):
            if response:
                return response

        if self.order_id:
            if not self.text:
                if not customer_facing:
                    return format_html(
                        '<a href="{}">{}</a>',
                        reverse(
                            "control:event.order",
                            kwargs={
                                "event": self.order.event.slug,
                                "organizer": self.order.event.organizer.slug,
                                "code": self.order.code,
                            }
                        ),
                        self.order.full_code
                    )
                return self.order.full_code
            else:
                return self.text
        else:
            if self.text:
                return format_html(
                    '<em>{}:</em> {}',
                    _('Manual transaction'),
                    self.text,
                )
            else:
                return _('Manual transaction')

    def display_backend(self):
        return self.display(customer_facing=False)

    def display_presale(self):
        return self.display(customer_facing=True)
