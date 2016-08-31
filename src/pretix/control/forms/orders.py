from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, Order


class ExtendForm(I18nModelForm):
    class Meta:
        model = Order
        fields = ['expires']


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
        label=_('New price')
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
            pname = i.name
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (pname, v.value)))
            else:
                choices.append((str(i.pk), pname))
        self.fields['itemvar'].choices = choices

    def clean(self):
        if self.cleaned_data.get('operation') == 'price' and not self.cleaned_data.get('price', '') != '':
            raise ValidationError(_('You need to enter a price if you want to change the product price.'))
