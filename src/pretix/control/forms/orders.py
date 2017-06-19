from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import localize
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.forms import I18nModelForm
from pretix.base.models import Item, ItemAddOn, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.services.pricing import get_price


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


class SubEventChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        p = get_price(self.instance.item, self.instance.variation,
                      voucher=self.instance.voucher,
                      subevent=obj)
        return '{} – {} ({} {})'.format(obj.name, obj.get_date_range_display(),
                                        p, self.instance.order.event.currency)


class OrderPositionAddForm(forms.Form):
    do = forms.BooleanField(
        label=_('Add a new product to the order'),
        required=False
    )
    itemvar = forms.ChoiceField(
        label=_('Product')
    )
    addon_to = forms.ModelChoiceField(
        OrderPosition.objects.none(),
        required=False,
        label=_('Add-on to'),
    )
    price = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        label=_('Gross price'),
        help_text=_("Keep empty for the product's default price")
    )
    subevent = forms.ModelChoiceField(
        SubEvent.objects.none(),
        label=_('Sub-event'),
        required=True,
        empty_label=None
    )

    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order')
        super().__init__(*args, **kwargs)
        choices = []
        for i in order.event.items.prefetch_related('variations').all():
            pname = str(i.name)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s (%s %s)' % (pname, v.value, localize(v.price),
                                                         order.event.currency)))
            else:
                choices.append((str(i.pk), '%s (%s %s)' % (pname, localize(i.default_price),
                                                           order.event.currency)))
        self.fields['itemvar'].choices = choices
        if ItemAddOn.objects.filter(base_item__event=order.event).exists():
            self.fields['addon_to'].queryset = order.positions.filter(addon_to__isnull=True).select_related(
                'item', 'variation'
            )
        else:
            del self.fields['addon_to']

        if order.event.has_subevents:
            self.fields['subevent'].queryset = order.event.subevents.all()
        else:
            del self.fields['subevent']


class OrderPositionChangeForm(forms.Form):
    itemvar = forms.ChoiceField()
    subevent = SubEventChoiceField(
        SubEvent.objects.none(),
        label=_('New sub-event'),
        required=True,
        empty_label=None
    )
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
            ('subevent', 'Change sub-event'),
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
        initial['subevent'] = instance.subevent

        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        if instance.order.event.has_subevents:
            self.fields['subevent'].instance = instance
            self.fields['subevent'].queryset = instance.order.event.subevents.all()
        else:
            del self.fields['subevent']
        choices = []
        for i in instance.order.event.items.prefetch_related('variations').all():
            pname = str(i.name)
            if not i.is_available():
                pname += ' ({})'.format(_('inactive'))
            variations = list(i.variations.all())
            if variations:
                for v in variations:
                    p = get_price(i, v, voucher=instance.voucher, subevent=instance.subevent)
                    choices.append(('%d-%d' % (i.pk, v.pk),
                                    '%s – %s (%s %s)' % (pname, v.value, localize(p),
                                                         instance.order.event.currency)))
            else:
                p = get_price(i, None, voucher=instance.voucher, subevent=instance.subevent)
                choices.append((str(i.pk), '%s (%s %s)' % (pname, localize(p),
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


class OrderLocaleForm(forms.ModelForm):
    locale = forms.ChoiceField()

    class Meta:
        model = Order
        fields = ['locale']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locale_names = dict(settings.LANGUAGES)
        self.fields['locale'].choices = [(a, locale_names[a]) for a in self.instance.event.settings.locales]
