from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import localize
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, Order


class ExtendForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['expires']
        widgets = {
            'expires': forms.DateInput(attrs={
                'class': 'datepickerfield',
                'data-is-payment-date': 'true'
            })
        }

    def clean(self):
        data = super().clean()
        data['expires'] = data['expires'].replace(hour=23, minute=59, second=59)
        if data['expires'] < now():
            raise ValidationError(_('The new expiry date needs to be in the future.'))
        return data


class ExporterForm(forms.Form):

    def clean(self):
        data = super().clean()

        for k, v in data.items():
            if isinstance(v, models.Model):
                data[k] = v.pk
            elif isinstance(v, models.QuerySet):
                data[k] = [m.pk for m in v]

        return data


class CommentForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'helper-width-100',
            }),
        }


class OrderPositionChangeForm(forms.Form):
    itemvar = forms.ChoiceField()
    price = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        label=_('New price (gross)')
    )
    operation = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect,
        choices=(
            ('product', 'Change product'),
            ('price', 'Change price'),
            ('cancel', 'Remove product')
        )
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance')
        initial = kwargs.get('initial', {})
        if instance:
            try:
                if instance.variation:
                    initial['itemvar'] = '%d-%d' % (instance.item.pk, instance.variation.pk)
                elif instance.item:
                    initial['itemvar'] = str(instance.item.pk)
            except Item.DoesNotExist:
                pass

            initial['price'] = instance.price

        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        choices = []
        for i in instance.order.event.items.prefetch_related('variations').all():
            pname = str(i.name)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s (%s %s)' % (pname, v.value, localize(v.price),
                                                         instance.order.event.currency)))
            else:
                choices.append((str(i.pk), '%s (%s %s)' % (pname, localize(i.default_price),
                                                           instance.order.event.currency)))
        self.fields['itemvar'].choices = choices

    def clean(self):
        if self.cleaned_data.get('operation') == 'price' and not self.cleaned_data.get('price', '') != '':
            raise ValidationError(_('You need to enter a price if you want to change the product price.'))


class OrderContactForm(forms.ModelForm):
    regenerate_secrets = forms.BooleanField(required=False, label=_('Invalidate secrets'),
                                            help_text=_('Regenerates the order and ticket secrets. You will '
                                                        'need to re-send the link to the order page to the user and '
                                                        'the user will need to download his tickets again. The old '
                                                        'versions will be invalid.'))

    class Meta:
        model = Order
        fields = ['email']
