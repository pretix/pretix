import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import localize
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField
from i18nfield.fields import I18nCharField

from pretix.base.decimal import round_decimal
from pretix.base.models.base import LoggedModel
from pretix.base.templatetags.money import money_filter


class TaxedPrice:
    def __init__(self, *, gross: Decimal, net: Decimal, tax: Decimal, rate: Decimal, name: str):
        if net + tax != gross:
            raise ValueError('Net value and tax value need to add to the gross value')
        self.gross = gross
        self.net = net
        self.tax = tax
        self.rate = rate
        self.name = name

    def __repr__(self):
        return '{} + {}% = {}'.format(localize(self.net), localize(self.rate), localize(self.gross))

    def print(self, currency):
        return '{} + {}% = {}'.format(
            money_filter(self.net, currency),
            localize(self.rate),
            money_filter(self.gross, currency)
        )

    def __sub__(self, other):
        newgross = self.gross - other.gross
        newnet = round_decimal(newgross - (newgross * (1 - 100 / (100 + self.rate)))).quantize(
            Decimal('10') ** self.gross.as_tuple().exponent
        )
        return TaxedPrice(
            gross=newgross,
            net=newnet,
            tax=newgross - newnet,
            rate=self.rate,
            name=self.name,
        )

    def __mul__(self, other):
        newgross = self.gross * other
        newnet = round_decimal(newgross - (newgross * (1 - 100 / (100 + self.rate)))).quantize(
            Decimal('10') ** self.gross.as_tuple().exponent
        )
        return TaxedPrice(
            gross=newgross,
            net=newnet,
            tax=newgross - newnet,
            rate=self.rate,
            name=self.name,
        )


TAXED_ZERO = TaxedPrice(
    gross=Decimal('0.00'),
    net=Decimal('0.00'),
    tax=Decimal('0.00'),
    rate=Decimal('0.00'),
    name=''
)

EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT',
    'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB'
}
EU_CURRENCIES = {
    'BG': 'BGN',
    'GB': 'GBP',
    'HR': 'HRK',
    'CZ': 'CZK',
    'DK': 'DKK',
    'HU': 'HUF',
    'PL': 'PLN',
    'RO': 'RON',
    'SE': 'SEK'
}


def cc_to_vat_prefix(country_code):
    if country_code == 'GR':
        return 'EL'
    return country_code


class TaxRule(LoggedModel):
    event = models.ForeignKey('Event', related_name='tax_rules', on_delete=models.CASCADE)
    name = I18nCharField(
        verbose_name=_('Name'),
        help_text=_('Should be short, e.g. "VAT"'),
        max_length=190,
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Tax rate")
    )
    price_includes_tax = models.BooleanField(
        verbose_name=_("The configured product prices include the tax amount"),
        default=True,
    )
    eu_reverse_charge = models.BooleanField(
        verbose_name=_("Use EU reverse charge taxation rules"),
        default=False,
        help_text=_("Not recommended. Most events will NOT be qualified for reverse charge since the place of "
                    "taxation is the location of the event. This option disables charging VAT for all customers "
                    "outside the EU and for business customers in different EU countries who entered a valid EU VAT "
                    "ID. Only enable this option after consulting a tax counsel. No warranty given for correct tax "
                    "calculation. USE AT YOUR OWN RISK.")
    )
    home_country = CountryField(
        verbose_name=_('Merchant country'),
        blank=True,
        help_text=_('Your country of residence. This is the country the EU reverse charge rule will not apply in, '
                    'if configured above.'),
    )
    custom_rules = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ('event', 'rate', 'id')

    def allow_delete(self):
        from pretix.base.models.orders import OrderFee, OrderPosition

        return (
            not OrderFee.objects.filter(tax_rule=self, order__event=self.event).exists()
            and not OrderPosition.all.filter(tax_rule=self, order__event=self.event).exists()
            and not self.event.items.filter(tax_rule=self).exists()
            and self.event.settings.tax_rate_default != self
        )

    @classmethod
    def zero(cls):
        return cls(
            event=None,
            name='',
            rate=Decimal('0.00'),
            price_includes_tax=True,
            eu_reverse_charge=False
        )

    def clean(self):
        if self.eu_reverse_charge and not self.home_country:
            raise ValidationError(_('You need to set your home country to use the reverse charge feature.'))

    def __str__(self):
        if self.price_includes_tax:
            s = _('incl. {rate}% {name}').format(rate=self.rate, name=self.name)
        else:
            s = _('plus {rate}% {name}').format(rate=self.rate, name=self.name)
        if self.eu_reverse_charge:
            s += ' ({})'.format(_('reverse charge enabled'))
        return str(s)

    @property
    def has_custom_rules(self):
        return self.custom_rules and self.custom_rules != '[]'

    def tax(self, base_price, base_price_is='auto', currency=None):
        from .event import Event
        try:
            currency = currency or self.event.currency
        except Event.DoesNotExist:
            pass
        if self.rate == Decimal('0.00'):
            return TaxedPrice(
                net=base_price, gross=base_price, tax=Decimal('0.00'),
                rate=self.rate, name=self.name
            )

        if base_price_is == 'auto':
            if self.price_includes_tax:
                base_price_is = 'gross'
            else:
                base_price_is = 'net'

        if base_price_is == 'gross':
            gross = base_price
            net = round_decimal(gross - (base_price * (1 - 100 / (100 + self.rate))),
                                currency)
        elif base_price_is == 'net':
            net = base_price
            gross = round_decimal((net * (1 + self.rate / 100)),
                                  currency)
        else:
            raise ValueError('Unknown base price type: {}'.format(base_price_is))

        return TaxedPrice(
            net=net, gross=gross, tax=gross - net,
            rate=self.rate, name=self.name
        )

    def get_matching_rule(self, invoice_address):
        rules = json.loads(self.custom_rules)
        if invoice_address:
            for r in rules:
                if r['country'] == 'EU' and str(invoice_address.country) not in EU_COUNTRIES:
                    continue
                if r['country'] not in ('ZZ', 'EU') and r['country'] != str(invoice_address.country):
                    continue
                if r['address_type'] == 'individual' and invoice_address.is_business:
                    continue
                if r['address_type'] in ('business', 'business_vat_id') and not invoice_address.is_business:
                    continue
                if r['address_type'] == 'business_vat_id' and (not invoice_address.vat_id or not invoice_address.vat_id_validated):
                    continue
                return r
        return {'action': 'vat'}

    def is_reverse_charge(self, invoice_address):
        if self.custom_rules:
            rule = self.get_matching_rule(invoice_address)
            return rule['action'] == 'reverse'

        if not self.eu_reverse_charge:
            return False

        if not invoice_address or not invoice_address.country:
            return False

        if str(invoice_address.country) not in EU_COUNTRIES:
            return False

        if invoice_address.country == self.home_country:
            return False

        if invoice_address.is_business and invoice_address.vat_id and invoice_address.vat_id_validated:
            return True

        return False

    def tax_applicable(self, invoice_address):
        if self.custom_rules:
            rule = self.get_matching_rule(invoice_address)
            return rule.get('action', 'vat') == 'vat'

        if not self.eu_reverse_charge:
            # No reverse charge rules? Always apply VAT!
            return True

        if not invoice_address or not invoice_address.country:
            # No country specified? Always apply VAT!
            return True

        if str(invoice_address.country) not in EU_COUNTRIES:
            # Non-EU country? Never apply VAT!
            return False

        if invoice_address.country == self.home_country:
            # Within same EU country? Always apply VAT!
            return True

        if invoice_address.is_business and invoice_address.vat_id and invoice_address.vat_id_validated:
            # Reverse charge case
            return False

        # Consumer in different EU country / invalid VAT
        return True

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()
