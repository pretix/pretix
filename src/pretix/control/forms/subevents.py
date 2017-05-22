from django import forms

from pretix.base.forms import I18nModelForm
from pretix.base.models.event import SubEvent


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
