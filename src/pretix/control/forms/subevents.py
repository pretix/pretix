from django import forms
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nInlineFormSet

from pretix.base.forms import I18nModelForm
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models.items import SubEventItem
from pretix.base.reldate import RelativeDateField, RelativeDateTimeField
from pretix.base.templatetags.money import money_filter
from pretix.control.forms import SplitDateTimePickerWidget
from pretix.helpers.money import change_decimal_field


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
            'frontpage_text'
        ]
        field_classes = {
            'date_from': forms.SplitDateTimeField,
            'date_to': forms.SplitDateTimeField,
            'date_admission': forms.SplitDateTimeField,
            'presale_start': forms.SplitDateTimeField,
            'presale_end': forms.SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'date_admission': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_presale_start_0'}),
        }


class SubEventBulkForm(SubEventForm):
    time_from = forms.TimeField(
        label=_('Event start time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield'})
    )
    time_to = forms.TimeField(
        label=_('Event end time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield'}),
        required=False
    )
    time_admission = forms.TimeField(
        label=_('Admission time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield'}),
        required=False
    )
    presale_start = RelativeDateTimeField(
        label=_('Start of presale'),
        help_text=_('Optional. No products will be sold before this date.'),
        required=False
    )
    presale_end = RelativeDateTimeField(
        label=_('End of presale'),
        help_text=_('Optional. No products will be sold after this date. If you do not set this value, the presale '
                    'will end after the end date of your event.'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'
        del self.fields['date_from']
        del self.fields['date_to']
        del self.fields['date_admission']


class SubEventItemOrVariationFormMixin:
    def __init__(self, *args, **kwargs):
        self.item = kwargs.pop('item')
        self.variation = kwargs.pop('variation', None)
        super().__init__(*args, **kwargs)
        change_decimal_field(self.fields['price'], self.item.event.currency)


class SubEventItemForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = money_filter(self.item.default_price, self.item.event.currency, hide_currency=True)
        self.fields['price'].label = str(self.item.name)

    class Meta:
        model = SubEventItem
        fields = ['price']
        widgets = {
            'price': forms.TextInput
        }


class SubEventItemVariationForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = money_filter(self.variation.price, self.item.event.currency, hide_currency=True)
        self.fields['price'].label = '{} – {}'.format(str(self.item.name), self.variation.value)

    class Meta:
        model = SubEventItem
        fields = ['price']
        widgets = {
            'price': forms.TextInput
        }


class QuotaFormSet(I18nInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        self.locales = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)

    @cached_property
    def items(self):
        return self.event.items.prefetch_related('variations').all()

    def _construct_form(self, i, **kwargs):
        kwargs['locales'] = self.locales
        kwargs['event'] = self.event
        kwargs['items'] = self.items
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            locales=self.locales,
            event=self.event,
            items=self.items
        )
        self.add_fields(form, None)
        return form


class SubEventMetaValueForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.property = kwargs.pop('property')
        self.default = kwargs.pop('default', None)
        super().__init__(*args, **kwargs)
        self.fields['value'].required = False
        self.fields['value'].widget.attrs['placeholder'] = self.default or self.property.default

    class Meta:
        model = SubEventMetaValue
        fields = ['value']
        widgets = {
            'value': forms.TextInput
        }


class CheckinListFormSet(I18nInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        self.locales = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)

    @cached_property
    def items(self):
        return self.event.items.prefetch_related('variations').all()

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            event=self.event,
        )
        self.add_fields(form, None)
        return form
