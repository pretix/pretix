from datetime import datetime, timedelta

from django import forms
from django.urls import reverse
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import pgettext_lazy
from django_scopes.forms import (
    SafeModelChoiceField, SafeModelMultipleChoiceField,
)

from pretix.base.channels import get_all_sales_channels
from pretix.base.models.checkin import CheckinList
from pretix.control.forms.widgets import Select2


class NextTimeField(forms.TimeField):
    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return
        tz = get_current_timezone()
        result = make_aware(datetime.combine(
            now().astimezone(tz).date(),
            value,
        ), tz)
        if result <= now():
            result += timedelta(days=1)
        return result


class CheckinListForm(forms.ModelForm):
    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.pop('locales', None)
        super().__init__(**kwargs)
        self.fields['limit_products'].queryset = self.event.items.all()
        self.fields['auto_checkin_sales_channels'] = forms.MultipleChoiceField(
            label=self.fields['auto_checkin_sales_channels'].label,
            help_text=self.fields['auto_checkin_sales_channels'].help_text,
            required=self.fields['auto_checkin_sales_channels'].required,
            choices=(
                (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
            ),
            widget=forms.CheckboxSelectMultiple
        )

        if not self.event.organizer.gates.exists():
            del self.fields['gates']
        else:
            self.fields['gates'].queryset = self.event.organizer.gates.all()

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']

    class Meta:
        model = CheckinList
        localized_fields = '__all__'
        fields = [
            'name',
            'all_products',
            'limit_products',
            'subevent',
            'include_pending',
            'auto_checkin_sales_channels',
            'allow_multiple_entries',
            'allow_entry_after_exit',
            'rules',
            'gates',
            'exit_all_at',
        ]
        widgets = {
            'limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]'
            }),
            'gates': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
            'auto_checkin_sales_channels': forms.CheckboxSelectMultiple(),
            'exit_all_at': forms.TimeInput(attrs={'class': 'timepickerfield'}),
        }
        field_classes = {
            'limit_products': SafeModelMultipleChoiceField,
            'gates': SafeModelMultipleChoiceField,
            'subevent': SafeModelChoiceField,
            'exit_all_at': NextTimeField,
        }


class SimpleCheckinListForm(forms.ModelForm):
    def __init__(self, **kwargs):
        self.event = kwargs.pop('event')
        kwargs.pop('locales', None)
        super().__init__(**kwargs)
        self.fields['limit_products'].queryset = self.event.items.all()

        if not self.event.organizer.gates.exists():
            del self.fields['gates']
        else:
            self.fields['gates'].queryset = self.event.organizer.gates.all()

    class Meta:
        model = CheckinList
        localized_fields = '__all__'
        fields = [
            'name',
            'all_products',
            'limit_products',
            'include_pending',
            'allow_entry_after_exit',
            'gates',
        ]
        widgets = {
            'limit_products': forms.CheckboxSelectMultiple(attrs={
                'data-inverse-dependency': '<[name$=all_products]'
            }),
            'gates': forms.CheckboxSelectMultiple(attrs={
                'class': 'scrolling-multiple-choice'
            }),
        }
        field_classes = {
            'limit_products': SafeModelMultipleChoiceField,
            'subevent': SafeModelChoiceField,
            'gates': SafeModelMultipleChoiceField,
        }
