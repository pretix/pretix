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

from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.models import Quota
from pretix.base.models.tax import TaxedPrice
from pretix.base.services.pricing import get_price
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.templatetags.money import money_filter


class OrderPositionChangeForm(forms.Form):
    itemvar = forms.ChoiceField(
        label=_('Product'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance')
        invoice_address = kwargs.pop('invoice_address')
        initial = kwargs.get('initial', {})
        event = kwargs.pop('event')
        hide_prices = kwargs.pop('hide_prices')
        quota_cache = kwargs.pop('quota_cache')
        kwargs['initial'] = initial
        if instance.variation_id:
            initial['itemvar'] = f'{instance.item_id}-{instance.variation_id}'
        else:
            initial['itemvar'] = f'{instance.item_id}'

        super().__init__(*args, **kwargs)

        choices = []

        i = instance.item
        pname = str(i.name)
        variations = list(i.variations.all())

        if variations and event.settings.change_allow_user_variation:
            current_quotas = (
                instance.variation.quotas.filter(subevent=instance.subevent)
                if instance.variation
                else instance.item.quotas.all(subevent=instance.subevent)
            )
            qa = QuotaAvailability()
            for v in variations:
                v._quotas = v.quotas.filter(subevent=instance.subevent)
                quotas_to_compute = [q for q in v._quotas if q not in quota_cache]
                qa.queue(*quotas_to_compute)
            qa.compute()
            quota_cache.update(qa.results)

            for v in variations:
                label = f'{i.name} – {v.value}'
                if instance.variation_id == v.id:
                    choices.append((f'{i.pk}-{v.pk}', label))
                    continue

                if instance.voucher and not instance.voucher.applies_to(i, v):
                    continue

                if v.hide_without_voucher and not (instance.voucher and instance.voucher.show_hidden_items):
                    continue

                if not v.active:
                    continue

                q_res = [
                    (qa.results[q] if q in qa.results else quota_cache[q])[0] != Quota.AVAILABILITY_OK
                    for q in v._quotas
                    if q not in current_quotas
                ]
                if not v._quotas or (q_res and any(q_res)):
                    continue

                new_price = get_price(i, v, voucher=instance.voucher, subevent=instance.subevent,
                                      invoice_address=invoice_address)
                current_price = TaxedPrice(tax=instance.tax_value, gross=instance.price, net=instance.price - instance.tax_value,
                                           name=instance.tax_rule.name if instance.tax_rule else '', rate=instance.tax_rate)
                if new_price.gross < current_price.gross and event.settings.change_allow_user_price == 'gte':
                    continue
                if new_price.gross <= current_price.gross and event.settings.change_allow_user_price == 'gt':
                    continue
                if new_price.gross != current_price.gross and event.settings.change_allow_user_price == 'eq':
                    continue

                if not hide_prices:
                    if new_price.gross < current_price.gross:
                        if event.settings.display_net_prices:
                            label += ' (- {} {})'.format(money_filter(current_price.gross - new_price.gross, event.currency), _('plus taxes'))
                        else:
                            label += ' (- {})'.format(money_filter(current_price.gross - new_price.gross, event.currency))
                    elif current_price.gross < new_price.gross:
                        if event.settings.display_net_prices:
                            label += ' ({}{} {})'.format(
                                '+ ' if current_price.gross != Decimal('0.00') else '',
                                money_filter(new_price.gross - current_price.gross, event.currency),
                                _('plus taxes')
                            )
                        else:
                            label += ' ({}{})'.format(
                                '+ ' if current_price.gross != Decimal('0.00') else '',
                                money_filter(new_price.gross - current_price.gross, event.currency)
                            )

                choices.append((f'{i.pk}-{v.pk}', label))

            if not choices:
                self.fields['itemvar'].widget.attrs['disabled'] = True
                self.fields['itemvar'].help_text = _('No other variation of this product is currently available for you.')
        else:
            choices.append((str(i.pk), '%s' % pname))
            self.fields['itemvar'].widget.attrs['disabled'] = True
            if event.settings.change_allow_user_variation:
                self.fields['itemvar'].help_text = _('No other variations of this product exist.')

        self.fields['itemvar'].choices = choices
