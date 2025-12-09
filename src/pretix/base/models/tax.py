#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
import json
from decimal import Decimal
from typing import Optional

from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.deconstruct import deconstructible
from django.utils.formats import localize
from django.utils.functional import lazy
from django.utils.hashable import make_hashable
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, pgettext, pgettext_lazy
from i18nfield.fields import I18nCharField
from i18nfield.strings import LazyI18nString

from pretix.base.decimal import round_decimal
from pretix.base.models.base import LoggedModel
from pretix.base.templatetags.money import money_filter
from pretix.helpers.countries import FastCountryField


class TaxedPrice:
    def __init__(self, *, gross: Decimal, net: Decimal, tax: Decimal, rate: Decimal, name: str, code: Optional[str]):
        if net + tax != gross:
            raise ValueError('Net value and tax value need to add to the gross value')
        self.gross = gross
        self.net = net
        self.tax = tax
        self.rate = rate
        self.name = name
        self.code = code

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
            code=self.code,
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
            code=self.code,
        )

    def __eq__(self, other):
        return (
            self.gross == other.gross and
            self.net == other.net and
            self.tax == other.tax and
            self.rate == other.rate and
            self.name == other.name and
            self.code == other.code
        )


TAXED_ZERO = TaxedPrice(
    gross=Decimal('0.00'),
    net=Decimal('0.00'),
    tax=Decimal('0.00'),
    rate=Decimal('0.00'),
    name='',
    code=None,
)

EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT',
    'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE',
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
VAT_ID_COUNTRIES = EU_COUNTRIES | {'CH', 'NO'}

format_html_lazy = lazy(format_html, str)


TAX_CODE_LISTS = (
    # Sources:
    # https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/Registry+of+supporting+artefacts+to+implement+EN16931#RegistryofsupportingartefactstoimplementEN16931-Codelists#RegistryofsupportingartefactstoimplementEN16931-Codelists
    # https://docs.peppol.eu/poacc/billing/3.0/codelist/vatex/
    # https://docs.peppol.eu/poacc/billing/3.0/codelist/UNCL5305/
    # https://www.bzst.de/DE/Unternehmen/Aussenpruefungen/DigitaleSchnittstelleFinV/digitaleschnittstellefinv_node.html#js-toc-entry2
    #
    # !! When changed, also update tax-rules-custom.schema.json and doc/api/resources/taxrules.rst !!
    (
        _("Standard rates"),
        (
            # Standard rate in any country, such as 19% in Germany or 20% in Austria
            # DSFinV-K mapping: 1
            ("S/standard", pgettext_lazy("tax_code", "Standard rate")),

            # Reduced rate in any country, such as 7% in Germany or both 10% and 13% in Austria
            # DSFinV-K mapping: 2
            ("S/reduced", pgettext_lazy("tax_code", "Reduced rate")),

            # Averaged rate, for example Germany § 24 (1) Nr. 3 UStG "für die übrigen Umsätze" in agricultural and silvicultural businesses
            # DSFinV-K mapping: 3
            ("S/averaged", pgettext_lazy("tax_code", "Averaged rate (other revenue in a agricultural and silvicultural business)")),

            # We ignore the German special case of the actual silvicultural products as they won't be sold through pretix (DSFinV-K mapping: 4)
        )
    ),
    (
        _("Reverse charge"),
        (
            ("AE", pgettext_lazy("tax_code", "Reverse charge")),
        )
    ),
    (
        _("Tax free"),
        (
            # DSFinV-K mapping: 5
            ("O", pgettext_lazy("tax_code", "Services outside of scope of tax")),

            # DSFinV-K mapping: 6
            ("E", pgettext_lazy("tax_code", "Exempt from tax (no reason given)")),

            # DSFinV-K mapping: 6
            ("Z", pgettext_lazy("tax_code", "Zero-rated goods")),

            # DSFinV-K mapping: 5
            ("G", pgettext_lazy("tax_code", "Free export item, VAT not charged")),

            # DSFinV-K mapping: 6?
            ("K", pgettext_lazy("tax_code", "VAT exempt for EEA intra-community supply of goods and services")),
        )
    ),
    (
        _("Special cases"),
        (
            ("L", pgettext_lazy("tax_code", "Canary Islands general indirect tax")),
            ("M", pgettext_lazy("tax_code", "Tax for production, services and importation in Ceuta and Melilla")),
            ("B", pgettext_lazy("tax_code", "Transferred (VAT), only in Italy")),
        )
    ),
    (
        _("Exempt with specific reason"),
        (
            ("E/VATEX-EU-79-C",
             pgettext_lazy("tax_code", "Exempt based on article 79, point c of Council Directive 2006/112/EC")),
            *[
                (
                    f"E/VATEX-EU-132-1{letter.upper()}",
                    lazy(
                        lambda let: pgettext(
                            "tax_code",
                            "Exempt based on article {article}, section {section} ({letter}) of Council "
                            "Directive 2006/112/EC"
                        ).format(article="132", section="1", letter=let),
                        str
                    )(letter)
                ) for letter in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q")
            ],
            *[
                (
                    f"E/VATEX-EU-143-1{letter.upper()}",
                    lazy(
                        lambda let: pgettext(
                            "tax_code",
                            "Exempt based on article {article}, section {section} ({letter}) of Council "
                            "Directive 2006/112/EC"
                        ).format(article="143", section="1", letter=let),
                        str
                    )(letter)
                ) for letter in ("a", "b", "c", "d", "e", "f", "fa", "g", "h", "i", "j", "k", "l")
            ],
            *[
                (
                    f"E/VATEX-EU-148-{letter.upper()}",
                    lazy(
                        lambda let: pgettext(
                            "tax_code",
                            "Exempt based on article {article}, section ({letter}) of Council "
                            "Directive 2006/112/EC"
                        ).format(article="148", letter=let),
                        str
                    )(letter)
                ) for letter in ("a", "b", "c", "d", "e", "f", "g")
            ],
            *[
                (
                    f"E/VATEX-EU-151-1{letter.upper()}",
                    lazy(
                        lambda let: pgettext(
                            "tax_code",
                            "Exempt based on article {article}, section {section} ({letter}) of Council "
                            "Directive 2006/112/EC"
                        ).format(article="151", section="1", letter=let),
                        str
                    )(letter)
                ) for letter in ("a", "aa", "b", "c", "d", "e")
            ],
            ("E/VATEX-EU-309",
             pgettext_lazy("tax_code", "Exempt based on article 309 of Council Directive 2006/112/EC")),
            ("E/VATEX-EU-D",
             pgettext_lazy("tax_code", "Intra-Community acquisition from second hand means of transport")),
            ("E/VATEX-EU-F",
             pgettext_lazy("tax_code", "Intra-Community acquisition of second hand goods")),
            ("E/VATEX-EU-I",
             pgettext_lazy("tax_code", "Intra-Community acquisition of works of art")),
            ("E/VATEX-EU-J",
             pgettext_lazy("tax_code", "Intra-Community acquisition of collectors items and antiques")),
            ("E/VATEX-FR-FRANCHISE",
             pgettext_lazy("tax_code", "France domestic VAT franchise in base")),
            ("E/VATEX-FR-CNWVAT",
             pgettext_lazy("tax_code", "France domestic Credit Notes without VAT, due to supplier forfeit of VAT for discount")),
        )
    ),
)


def get_tax_code_labels():
    flat = []
    for choice, value in TAX_CODE_LISTS:
        if isinstance(value, (list, tuple)):
            flat.extend(value)
        else:
            flat.append((choice, value))

    return dict(make_hashable(flat))


def is_eu_country(cc):
    cc = str(cc)
    return cc in EU_COUNTRIES


def ask_for_vat_id(cc):
    cc = str(cc)
    return cc in VAT_ID_COUNTRIES


def cc_to_vat_prefix(country_code):
    country_code = str(country_code)
    if country_code == 'GR':
        return 'EL'
    return country_code


@deconstructible
class CustomRulesValidator:
    def __call__(self, value):
        import jsonschema

        if not isinstance(value, dict):
            try:
                val = json.loads(value)
            except ValueError:
                raise ValidationError(_('Your layout file is not a valid JSON file.'))
        else:
            val = value
        with open(finders.find('schema/tax-rules-custom.schema.json'), 'r') as f:
            schema = json.loads(f.read())
        try:
            jsonschema.validate(val, schema)
        except jsonschema.ValidationError as e:
            e = str(e).replace('%', '%%')
            raise ValidationError(_('Your set of rules is not valid. Error message: {}').format(e))


class TaxRule(LoggedModel):
    event = models.ForeignKey('Event', related_name='tax_rules', on_delete=models.CASCADE)
    internal_name = models.CharField(
        verbose_name=_('Internal name'),
        max_length=190,
        null=True, blank=True,
    )
    name = I18nCharField(
        verbose_name=_('Official name'),
        help_text=_('Should be short, e.g. "VAT"'),
        max_length=190,
    )
    code = models.CharField(
        verbose_name=_('Tax code'),
        help_text=_('If you help us understand what this tax rules legally is, we can use this information for '
                    'eInvoices, exporting to accounting system, etc.'),
        null=True, blank=True,
        max_length=190,
        choices=TAX_CODE_LISTS,
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MaxValueValidator(
                limit_value=Decimal("100.00"),
            ),
            MinValueValidator(
                limit_value=Decimal("0.00"),
            ),
        ],
        verbose_name=_("Tax rate"),
    )
    price_includes_tax = models.BooleanField(
        verbose_name=_("The configured product prices include the tax amount"),
        default=True,
    )
    keep_gross_if_rate_changes = models.BooleanField(
        verbose_name=_("Keep gross amount constant if the tax rate changes based on the invoice address"),
        default=False,
    )
    eu_reverse_charge = models.BooleanField(
        verbose_name=_("Use EU reverse charge taxation rules"),
        default=False,
        help_text=format_html_lazy(
            '<span class="label label-warning" data-toggle="tooltip" title="{}">{}</span> {}',
            _('This feature will be removed in the future as it does not handle VAT for non-business customers in '
              'other EU countries in a way that works for all organizers. Use custom rules instead.'),
            _('DEPRECATED'),
            _("Not recommended. Most events will NOT be qualified for reverse charge since the place of "
              "taxation is the location of the event. This option disables charging VAT for all customers "
              "outside the EU and for business customers in different EU countries who entered a valid EU VAT "
              "ID. Only enable this option after consulting a tax counsel. No warranty given for correct tax "
              "calculation. USE AT YOUR OWN RISK.")
        ),
    )
    home_country = FastCountryField(
        verbose_name=_('Merchant country'),
        blank=True,
        help_text=_('Your country of residence. This is the country the EU reverse charge rule will not apply in, '
                    'if configured above.'),
    )
    custom_rules = models.TextField(blank=True, null=True)
    default = models.BooleanField(
        verbose_name=_('Default'),
        default=False,
    )

    class Meta:
        ordering = ('event', 'rate', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=["event"],
                condition=models.Q(default=True),
                name="one_default_per_event",
            ),
        ]

    class SaleNotAllowed(Exception):
        pass

    def allow_delete(self):
        from pretix.base.models.orders import (
            OrderFee, OrderPosition, Transaction,
        )

        return (
            not Transaction.objects.filter(tax_rule=self, order__event=self.event).exists()
            and not OrderFee.objects.filter(tax_rule=self, order__event=self.event).exists()
            and not OrderPosition.all.filter(tax_rule=self, order__event=self.event).exists()
            and not self.event.items.filter(tax_rule=self).exists()
            and not (self.default and self.event.tax_rules.filter(~models.Q(pk=self.pk)).exists())
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

        if self.rate != Decimal("0.00") and self.code and (self.code.split("/")[0] in ("O", "E", "Z", "G", "K", "AE")):
            raise ValidationError({
                "code": _("A combination of this tax code with a non-zero tax rate does not make sense.")
            })

        if self.rate == Decimal("0.00") and self.code and (self.code.split("/")[0] in ("S", "L", "M", "B")):
            raise ValidationError({
                "code": _("A combination of this tax code with a zero tax rate does not make sense.")
            })

    def __str__(self):
        if self.price_includes_tax:
            s = _('incl. {rate}% {name}').format(rate=self.rate, name=self.name)
        else:
            s = _('plus {rate}% {name}').format(rate=self.rate, name=self.name)
        if self.eu_reverse_charge:
            s += ' ({})'.format(_('reverse charge enabled'))
        if self.internal_name:
            return f'{self.internal_name} ({s})'
        return str(s)

    @property
    def has_custom_rules(self):
        return self.custom_rules and self.custom_rules != '[]'

    def tax_rate_for(self, invoice_address):
        if not self._tax_applicable(invoice_address):
            return Decimal('0.00')
        if self.has_custom_rules:
            rule = self.get_matching_rule(invoice_address)
            if rule.get('action', 'vat') == 'block':
                raise self.SaleNotAllowed()
            if rule.get('action', 'vat') in ('vat', 'require_approval') and rule.get('rate') is not None:
                return Decimal(rule.get('rate'))
        return Decimal(self.rate)

    def tax(self, base_price, base_price_is='auto', currency=None, override_tax_rate=None, override_tax_code=None,
            invoice_address=None, subtract_from_gross=Decimal('0.00'), gross_price_is_tax_rate: Decimal = None,
            force_fixed_gross_price=False):
        from .event import Event
        try:
            currency = currency or self.event.currency
        except Event.DoesNotExist:
            pass

        rate = Decimal(self.rate)
        code = self.code

        if override_tax_code is not None:
            code = override_tax_code
        elif invoice_address:
            code = self.tax_code_for(invoice_address)

        if override_tax_rate is not None:
            rate = override_tax_rate
        elif invoice_address:
            adjust_rate = self.tax_rate_for(invoice_address)
            if (adjust_rate == gross_price_is_tax_rate or force_fixed_gross_price or self.keep_gross_if_rate_changes) and base_price_is == 'gross':
                rate = adjust_rate
            elif adjust_rate != rate:
                if self.keep_gross_if_rate_changes:
                    normal_price = self.tax(base_price, base_price_is, currency, subtract_from_gross=subtract_from_gross)
                    base_price = normal_price.gross
                    base_price_is = 'gross'
                    subtract_from_gross = Decimal('0.00')
                else:
                    normal_price = self.tax(base_price, base_price_is, currency, subtract_from_gross=subtract_from_gross)
                    base_price = normal_price.net
                    base_price_is = 'net'
                    subtract_from_gross = Decimal('0.00')
                rate = adjust_rate

        def _limit_subtract(base_price, subtract_from_gross):
            if not subtract_from_gross:
                return base_price
            if base_price >= Decimal('0.00'):
                # For positive prices, make sure they don't go negative because of bundles
                return max(Decimal('0.00'), base_price - subtract_from_gross)
            else:
                # If the price is already negative, we don't really care any more
                return base_price - subtract_from_gross

        if rate == Decimal('0.00'):
            gross = _limit_subtract(base_price, subtract_from_gross)
            return TaxedPrice(
                net=gross, gross=gross, tax=Decimal('0.00'),
                rate=rate, name=self.name, code=code,
            )

        if base_price_is == 'auto':
            if self.price_includes_tax:
                base_price_is = 'gross'
            else:
                base_price_is = 'net'

        if base_price_is == 'gross':
            gross = _limit_subtract(base_price, subtract_from_gross)
            net = round_decimal(gross - (gross * (1 - 100 / (100 + rate))),
                                currency)
        elif base_price_is == 'net':
            net = base_price
            gross = round_decimal((net * (1 + rate / 100)), currency)
            if subtract_from_gross:
                gross = _limit_subtract(gross, subtract_from_gross)
                net = round_decimal(gross - (gross * (1 - 100 / (100 + rate))),
                                    currency)
        else:
            raise ValueError('Unknown base price type: {}'.format(base_price_is))

        return TaxedPrice(
            net=net, gross=gross, tax=gross - net,
            rate=rate, name=self.name, code=code,
        )

    @property
    def _custom_rules(self):
        if not self.custom_rules:
            return []
        return json.loads(self.custom_rules)

    def get_matching_rule(self, invoice_address):
        rules = self._custom_rules
        if invoice_address:
            for r in rules:
                if r['country'] == 'ZZ':    # Rule: Any country
                    pass
                elif r['country'] == 'EU':  # Rule: Any EU country
                    if not is_eu_country(invoice_address.country):
                        continue
                elif '-' in r['country']:   # Rule: Specific country and state
                    if r['country'] != str(invoice_address.country) + '-' + str(invoice_address.state):
                        continue
                else:                       # Rule: Specific country
                    if r['country'] != str(invoice_address.country):
                        continue
                if r['address_type'] == 'individual' and invoice_address.is_business:
                    continue
                if r['address_type'] in ('business', 'business_vat_id') and not invoice_address.is_business:
                    continue
                if r['address_type'] == 'business_vat_id' and (not invoice_address.vat_id or not invoice_address.vat_id_validated):
                    continue
                return r
        return {'action': 'vat'}

    def invoice_text(self, invoice_address):
        if self._custom_rules:
            rule = self.get_matching_rule(invoice_address)
            t = rule.get('invoice_text', {})
            if t and any(l for l in t.values()):
                return str(LazyI18nString(t))
        if self.is_reverse_charge(invoice_address):
            if is_eu_country(invoice_address.country):
                return pgettext(
                    "invoice",
                    "Reverse Charge: According to Article 194, 196 of Council Directive 2006/112/EEC, VAT liability "
                    "rests with the service recipient."
                )
            else:
                return pgettext(
                    "invoice",
                    "VAT liability rests with the service recipient."
                )

    def is_reverse_charge(self, invoice_address):
        if self._custom_rules:
            rule = self.get_matching_rule(invoice_address)
            return rule['action'] == 'reverse'

        if not self.eu_reverse_charge:
            return False

        if not invoice_address or not invoice_address.country:
            return False

        if not is_eu_country(invoice_address.country):
            return False

        if invoice_address.country == self.home_country:
            return False

        if invoice_address.is_business and invoice_address.vat_id and invoice_address.vat_id_validated:
            return True

        return False

    def _require_approval(self, invoice_address):
        if self._custom_rules:
            rule = self.get_matching_rule(invoice_address)
            if rule.get('action', 'vat') == 'require_approval':
                return True
        return False

    def tax_code_for(self, invoice_address):
        if self._custom_rules:
            rule = self.get_matching_rule(invoice_address)
            if rule.get("code"):
                return rule["code"]
            if rule.get("action", "vat") == "reverse":
                return "AE"
            return self.code

        if not self.eu_reverse_charge:
            # No reverse charge rules? Always apply VAT!
            return self.code

        if not invoice_address or not invoice_address.country:
            # No country specified? Always apply VAT!
            return self.code

        if not is_eu_country(invoice_address.country):
            # Non-EU country? "Non-taxable" since not in scope
            return "O"

        if invoice_address.country == self.home_country:
            # Within same EU country? Always apply VAT!
            return self.code

        if invoice_address.is_business and invoice_address.vat_id and invoice_address.vat_id_validated:
            # Reverse charge case
            return "AE"

        # Consumer in different EU country / invalid VAT
        return self.code

    def _tax_applicable(self, invoice_address):
        if self._custom_rules:
            rule = self.get_matching_rule(invoice_address)
            if rule.get('action', 'vat') == 'block':
                raise self.SaleNotAllowed()
            return rule.get('action', 'vat') in ('vat', 'require_approval')

        if not self.eu_reverse_charge:
            # No reverse charge rules? Always apply VAT!
            return True

        if not invoice_address or not invoice_address.country:
            # No country specified? Always apply VAT!
            return True

        if not is_eu_country(invoice_address.country):
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
