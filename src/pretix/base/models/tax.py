from django.db import models
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField

from pretix.base.models.base import LoggedModel


class TaxRule(LoggedModel):
    event = models.ForeignKey('Event', related_name='tax_rules')
    name = I18nCharField(
        verbose_name=_('Name'),
        help_text=_('Should be short, e.g. "VAT"'),
        max_length=190
    )
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Tax rate")
    )
    price_includes_tax = models.BooleanField(
        verbose_name=_("The configured product prices includes the tax amount"),
        default=True,
    )
    eu_reverse_charge = models.BooleanField(
        verbose_name=_("Use EU reverse charge taxation"),
        default=False,
        help_text=_("Not recommended. Most events will NOT be qualified for reverse charge since the place of "
                    "taxation is the location of the event. This option only enables reverse charge for business "
                    "customers who entered a valid EU VAT ID. Only enable this option after consulting a tax counsel. "
                    "No warranty given for correct tax calculation.")
    )
    home_country = models.CharField(
        verbose_name=_('Merchant country'),
        blank=True,
        help_text=_('Your country. Only relevant for EU reverse charge.'),
        max_length=2,
        choices=(
            ('AT', _('Austria')),
            ('BE', _('Belgium')),
            ('BG', _('Bulgaria')),
            ('HR', _('Croatia')),
            ('CY', _('Cyprus')),
            ('CZ', _('Czech Republic')),
            ('DK', _('Denmark')),
            ('EE', _('Estonia')),
            ('FI', _('Finland')),
            ('FR', _('France')),
            ('DE', _('Germany')),
            ('GR', _('Greece')),
            ('HU', _('Hungary')),
            ('IE', _('Ireland')),
            ('IT', _('Italy')),
            ('LV', _('Latvia')),
            ('LT', _('Lithuania')),
            ('LU', _('Luxembourg')),
            ('MT', _('Malta')),
            ('NL', _('Netherlands')),
            ('PL', _('Poland')),
            ('PT', _('Portugal')),
            ('RO', _('Romania')),
            ('SK', _('Slovakia')),
            ('SI', _('Slovenia')),
            ('ES', _('Spain')),
            ('SE', _('Sweden')),
            ('UJ', _('United Kingdom')),
        )
    )

    def clean(self):
        if self.eu_reverse_charge and not self.home_country:
            raise ValueError(_('You need to set your home country to use the reverse charge feature.'))

    def __str__(self):
        if self.price_includes_tax:
            s = _('incl. {rate} {name}').format(rate=self.rate, name=self.name)
        else:
            s = _('plus {rate} {name}').format(rate=self.rate, name=self.name)
        if self.eu_reverse_charge:
            s += ' ({})'.format(_('reverse charge enabled'))
        return str(s)
