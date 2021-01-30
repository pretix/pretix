from datetime import timedelta
from urllib.parse import urlencode

from django import forms
from django.forms import formset_factory
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.dates import MONTHS, WEEKDAYS
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from i18nfield.forms import I18nInlineFormSet

from pretix.base.forms import I18nModelForm
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models.items import SubEventItem
from pretix.base.reldate import RelativeDateTimeField
from pretix.base.templatetags.money import money_filter
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.helpers.money import change_decimal_field


class SubEventForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        instance = kwargs.get('instance')
        if instance and not instance.pk:
            kwargs['initial'].setdefault('name', self.event.name)
            kwargs['initial'].setdefault('location', self.event.location)
            kwargs['initial'].setdefault('geo_lat', self.event.geo_lat)
            kwargs['initial'].setdefault('geo_lon', self.event.geo_lon)
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'

    class Meta:
        model = SubEvent
        localized_fields = '__all__'
        fields = [
            'name',
            'active',
            'is_public',
            'date_from',
            'date_to',
            'date_admission',
            'presale_start',
            'presale_end',
            'location',
            'frontpage_text',
            'geo_lat',
            'geo_lon',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'date_admission': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'date_admission': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_presale_start_0'}),
        }


class SubEventBulkForm(SubEventForm):
    rel_presale_start = RelativeDateTimeField(
        label=_('Start of presale'),
        help_text=_('Optional. No products will be sold before this date.'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )
    rel_presale_end = RelativeDateTimeField(
        label=_('End of presale'),
        help_text=_('Optional. No products will be sold after this date. If you do not set this value, the presale '
                    'will end after the end date of your event.'),
        required=False,
        limit_choices=('date_from', 'date_to'),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs['event']
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'
        del self.fields['date_from']
        del self.fields['date_to']
        del self.fields['date_admission']


class NullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('Keep the current values')),
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


class SubEventBulkEditForm(I18nModelForm):
    def __init__(self, *args, **kwargs):
        self.mixed_values = kwargs.pop('mixed_values')
        self.queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        self.fields['location'].widget.attrs['rows'] = '3'

        for k in ('name', 'location', 'frontpage_text'):
            # i18n fields
            if k in self.mixed_values:
                self.fields[k].widget.attrs['placeholder'] = _('Keep the current values')
            else:
                self.fields[k].widget.attrs['placeholder'] = ''
            self.fields[k].one_required = False

        for k in ('geo_lat', 'geo_lon'):
            # scalar fields
            if k in self.mixed_values:
                self.fields[k].widget.attrs['placeholder'] = _('Keep the current values')
            else:
                self.fields[k].widget.attrs['placeholder'] = ''
            self.fields[k].widget.is_required = False
            self.fields[k].required = False

    class Meta:
        model = SubEvent
        localized_fields = '__all__'
        fields = [
            'name',
            'location',
            'frontpage_text',
            'geo_lat',
            'geo_lon',
            'is_public',
            'active',
        ]
        field_classes = {
            'is_public': forms.NullBooleanField,
            'active': forms.NullBooleanField,
        }
        widgets = {
            'is_public': NullBooleanSelect,
            'active': NullBooleanSelect,
        }

    def save(self, commit=True):
        objs = list(self.queryset)
        fields = set()
        for k in self.changed_data:
            # i18n and scalar fields
            if k in ('name', 'location', 'frontpage_text', 'geo_lat', 'geo_lon') and self.cleaned_data[k]:
                fields.add(k)
                for obj in objs:
                    setattr(obj, k, self.cleaned_data[k])
            if k in ('active', 'is_public') and self.cleaned_data[k] is not None:
                fields.add(k)
                for obj in objs:
                    setattr(obj, k, self.cleaned_data[k])
        if fields:
            SubEvent.objects.bulk_update(objs, fields, 200)

    def full_clean(self):
        if len(self.data) == 0:
            # form wasn't submitted
            self._errors = ErrorDict()
            return
        super().full_clean()


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
        self.fields['price'].label = str(self.item)

    class Meta:
        model = SubEventItem
        fields = ['price', 'disabled']
        widgets = {
            'price': forms.TextInput
        }


class SubEventItemVariationForm(SubEventItemOrVariationFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].widget.attrs['placeholder'] = money_filter(self.variation.price, self.item.event.currency, hide_currency=True)
        self.fields['price'].label = '{} – {}'.format(str(self.item), self.variation.value)

    class Meta:
        model = SubEventItem
        fields = ['price', 'disabled']
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
        kwargs['items'] = self.items
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            use_required_attribute=False,
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
        self.disabled = kwargs.pop('disabled')
        super().__init__(*args, **kwargs)
        if self.property.allowed_values:
            self.fields['value'] = forms.ChoiceField(
                label=self.property.name,
                choices=[
                    ('', _('Default ({value})').format(value=self.default or self.property.default) if self.default or self.property.default else ''),
                ] + [(a.strip(), a.strip()) for a in self.property.allowed_values.splitlines()],
            )
        else:
            self.fields['value'].label = self.property.name
            self.fields['value'].widget.attrs['placeholder'] = self.default or self.property.default
            self.fields['value'].widget.attrs['data-typeahead-url'] = (
                reverse('control:events.meta.typeahead') + '?' + urlencode({
                    'property': self.property.name,
                    'organizer': self.property.organizer.slug,
                })
            )
        self.fields['value'].required = False
        if self.disabled:
            self.fields['value'].widget.attrs['readonly'] = 'readonly'

    def clean_slug(self):
        if self.disabled:
            return self.instance.value if self.instance else None
        return self.cleaned_data['slug']

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
            use_required_attribute=False,
            event=self.event,
        )
        self.add_fields(form, None)
        return form


class RRuleForm(forms.Form):
    # TODO: calendar.setfirstweekday
    exclude = forms.BooleanField(
        label=_('Exclude these dates instead of adding them.'),
        required=False
    )
    freq = forms.ChoiceField(
        choices=[
            ('yearly', _('year(s)')),
            ('monthly', _('month(s)')),
            ('weekly', _('week(s)')),
            ('daily', _('day(s)')),
        ],
        initial='weekly'
    )
    interval = forms.IntegerField(
        label=_('Interval'),
        initial=1
    )
    dtstart = forms.DateField(
        label=_('Start date'),
        widget=forms.DateInput(
            attrs={
                'class': 'datepickerfield',
                'required': 'required'
            }
        ),
        initial=lambda: now().date()
    )

    end = forms.ChoiceField(
        choices=[
            ('count', ''),
            ('until', ''),
        ],
        initial='count',
        widget=forms.RadioSelect
    )
    count = forms.IntegerField(
        label=_('Number of repetitions'),
        initial=10
    )
    until = forms.DateField(
        widget=forms.DateInput(
            attrs={
                'class': 'datepickerfield',
                'required': 'required'
            }
        ),
        label=_('Last date'),
        required=True,
        initial=lambda: now() + timedelta(days=365)
    )

    yearly_bysetpos = forms.ChoiceField(
        choices=[
            ('1', pgettext_lazy('rrule', 'first')),
            ('2', pgettext_lazy('rrule', 'second')),
            ('3', pgettext_lazy('rrule', 'third')),
            ('-1', pgettext_lazy('rrule', 'last')),
        ],
        required=False
    )
    yearly_same = forms.ChoiceField(
        choices=[
            ('on', ''),
            ('off', ''),
        ],
        initial='on',
        widget=forms.RadioSelect
    )
    yearly_byweekday = forms.ChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
            ('MO,TU,WE,TH,FR,SA,SU', _('Day')),
            ('MO,TU,WE,TH,FR', _('Weekday')),
            ('SA,SU', _('Weekend day')),
        ],
        required=False
    )
    yearly_bymonth = forms.ChoiceField(
        choices=[
            (str(i), MONTHS[i]) for i in range(1, 13)
        ],
        required=False
    )

    monthly_same = forms.ChoiceField(
        choices=[
            ('on', ''),
            ('off', ''),
        ],
        initial='on',
        widget=forms.RadioSelect
    )
    monthly_bysetpos = forms.ChoiceField(
        choices=[
            ('1', pgettext_lazy('rrule', 'first')),
            ('2', pgettext_lazy('rrule', 'second')),
            ('3', pgettext_lazy('rrule', 'third')),
            ('-1', pgettext_lazy('rrule', 'last')),
        ],
        required=False
    )
    monthly_byweekday = forms.ChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
            ('MO,TU,WE,TH,FR,SA,SU', _('Day')),
            ('MO,TU,WE,TH,FR', _('Weekday')),
            ('SA,SU', _('Weekend day')),
        ],
        required=False
    )

    weekly_byweekday = forms.MultipleChoiceField(
        choices=[
            ('MO', WEEKDAYS[0]),
            ('TU', WEEKDAYS[1]),
            ('WE', WEEKDAYS[2]),
            ('TH', WEEKDAYS[3]),
            ('FR', WEEKDAYS[4]),
            ('SA', WEEKDAYS[5]),
            ('SU', WEEKDAYS[6]),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def parse_weekdays(self, value):
        m = {
            'MO': 0,
            'TU': 1,
            'WE': 2,
            'TH': 3,
            'FR': 4,
            'SA': 5,
            'SU': 6
        }
        if ',' in value:
            return [m.get(a) for a in value.split(',')]
        else:
            return m.get(value)


RRuleFormSet = formset_factory(
    RRuleForm,
    can_order=False, can_delete=True, extra=1
)


class TimeForm(forms.Form):
    time_from = forms.TimeField(
        label=_('Event start time'),
        widget=forms.TimeInput(attrs={'class': 'timepickerfield'}),
        required=True
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


TimeFormSet = formset_factory(
    TimeForm,
    min_num=1,
    can_order=False, can_delete=True, extra=1, validate_min=True
)
