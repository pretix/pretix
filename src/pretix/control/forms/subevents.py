from django import forms
from i18nfield.forms import I18nInlineFormSet

from pretix.base.forms import I18nModelForm
from pretix.base.models.event import SubEvent
from pretix.base.models.items import SubEventItem


class SubEventForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'

    class Meta:
        model = SubEvent
        localized_fields = '__all__'
        fields = [
            'name',
            'active',
            'date_from',
            'date_to',
            'date_admission',
            'presale_start',
            'presale_end',
            'location',
        ]
        widgets = {
            'date_from': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'date_to': forms.DateTimeInput(attrs={'class': 'datetimepicker', 'data-date-after': '#id_date_from'}),
            'date_admission': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'presale_start': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'presale_end': forms.DateTimeInput(attrs={'class': 'datetimepicker',
                                                      'data-date-after': '#id_presale_start'}),
        }


class SubEventItemOrVariationFormMixin:
    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop('item')
        self.variation = kwargs.pop('variation', None)
        super().__init__(*args, **kwargs)


class SubEventItemForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = '{} {}'.format(
            self.item.default_price, self.item.event.currency
        )

    class Meta:
        model = SubEventItem
        fields = ['price']


class SubEventItemVariationForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = '{} {}'.format(
            self.variation.price, self.item.event.currency
        )

    class Meta:
        model = SubEventItem
        fields = ['price']


class QuotaFormSet(I18nInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        self.locales = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['locales'] = self.locales
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            locales=self.locales,
            event=self.event
        )
        self.add_fields(form, None)
        return form
