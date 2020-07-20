from decimal import Decimal

from django import forms
from django.utils.translation import ugettext_lazy as _

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
        kwargs['initial'] = initial
        if instance.variation_id:
            initial['itemvar'] = f'{instance.item_id}-{instance.variation_id}'
        else:
            initial['itemvar'] = f'{instance.item_id}'

        super().__init__(*args, **kwargs)

        choices = []

        i = instance.item
        pname = str(i)
        variations = list(i.variations.all())

        if variations:
            current_quotas = instance.variation.quotas.all() if instance.variation else instance.item.quotas.all()
            qa = QuotaAvailability()
            for v in variations:
                qa.queue(*v.quotas.all())
            qa.compute()

            for v in variations:

                label = f'{i.name} – {v.value}'
                if instance.variation_id == v.id:
                    choices.append((f'{i.pk}-{v.pk}', label))
                    continue

                if not v.active:
                    continue

                q_res = [qa.results[q][0] != Quota.AVAILABILITY_OK for q in v.quotas.all() if q not in current_quotas]
                if not v.quotas.all() or (q_res and any(q_res)):
                    continue

                new_price = get_price(i, v, voucher=instance.voucher, subevent=instance.subevent,
                                      invoice_address=invoice_address)
                current_price = TaxedPrice(tax=instance.tax_value, gross=instance.price, net=instance.price - instance.tax_value,
                                           name=instance.tax_rule.name if instance.tax_rule else '', rate=instance.tax_rate)
                if new_price.gross < current_price.gross and event.settings.change_allow_user_price == 'gt':
                    continue
                if new_price.gross != current_price.gross and event.settings.change_allow_user_price == 'eq':
                    continue

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
        else:
            choices.append((str(i.pk), '%s' % pname))
        self.fields['itemvar'].choices = choices
