from ast import literal_eval
from collections import namedtuple
from datetime import datetime
from typing import Union

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import Event
from pretix.control.forms import SplitDateTimeField
from pretix.control.forms.widgets import Select2

SubEventSelection = namedtuple(
    typename='SubEventSelection',
    field_names=['selection', 'subevents', 'start', 'end', ],
    defaults=['subevent', None, None, None],
)


subeventselectionparts = namedtuple(
    typename='subeventselectionparts',
    field_names=['selection', 'subevents', 'start', 'end']
)


class SubEventSelectionWrapper:
    def __init__(self, data: Union[None, SubEventSelection]):
        self.data = data

    def get_queryset(self, event: Event):
        if self.data.selection == 'subevent':
            if self.data.subevents is None:
                return event.subevents.all()
            else:
                return event.subevents.filter(pk=self.data.subevents)
        elif self.data.selection == 'timerange':
            if self.data.start and self.data.end:
                return event.subevents.filter(date_from__lte=self.data.start,
                                              date_from__gte=self.data.end)
            elif self.data.start:
                return event.subevents.filter(date_from__gte=self.data.start)
            elif self.data.end:
                return event.subevents.filter(date_from__lte=self.data.end)
        return event.subevents.all()

    def to_string(self) -> str:
        if self.data:
            if self.data.selection == 'subevent':
                return 'SUBEVENT/pk/{}'.format(self.data.subevents.pk)
            elif self.data.selection == 'timerange':
                if self.data.start and self.data.end:
                    return 'SUBEVENT/range/{}/{}'.format(self.data.start.isoformat(), self.data.end.isoformat())
                elif self.data.start:
                    return 'SUBEVENT/from/{}'.format(self.data.start)
                elif self.data.end:
                    return 'SUBEVENT/to/{}'.format(self.data.end)
        return 'SUBEVENT'

    @classmethod
    def from_string(cls, input: str):
        data = SubEventSelection(selection='subevent')

        if input.startswith('SUBEVENT'):
            parts = input.split('/')
            if len(parts) == 1:
                data = SubEventSelection(selection='subevent')
            elif parts[1] == 'pk':
                data = SubEventSelection(
                    selection='subevent',
                    subevents=literal_eval(parts[2])
                )
            elif parts[1] == 'range':
                data = SubEventSelection(
                    selection="timerange",
                    start=datetime.fromisoformat(parts[2]),
                    end=datetime.fromisoformat(parts[3]),
                )
            elif parts[1] == 'from':
                data = SubEventSelection(
                    selection="timerange",
                    start=datetime.fromisoformat(parts[2]),
                )
            elif parts[1] == 'to':
                data = SubEventSelection(
                    selection="timerange",
                    end=datetime.fromisoformat(parts[3]),
                )
        return SubEventSelectionWrapper(
            data=data
        )


class SubeventSelectionWidget(forms.MultiWidget):
    template_name = 'pretixcontrol/forms/widgets/subeventselection.html'
    parts = SubEventSelection

    def __init__(self, event: Event, status_choices, subevent_choices, *args, **kwargs):
        widgets = subeventselectionparts(
            selection=forms.RadioSelect(
                choices=status_choices,

            ),
            subevents=Select2(
                attrs={
                    'class': 'simple-subevent-choice',
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                },
            ),
            start=SplitDateTimePickerWidget(),
            end=SplitDateTimePickerWidget(),

        )
        widgets.subevents.choices = subevent_choices
        super().__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):

        if isinstance(value, str):
            value = SubEventSelectionWrapper.from_string(value)
            if isinstance(value, subeventselectionparts):
                return value

        return subeventselectionparts(selection='subevent', start=None, end=None, subevents=None)


class SubeventSelectionField(forms.MultiValueField):
    widget = SubeventSelectionWidget

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')

        choices = [
            ("subevent", _("Subevent")),
            ("timerange", _("Timerange"))
        ]

        fields = SubEventSelection(
            selection=forms.ChoiceField(
                choices=choices,
                required=True,
            ),
            subevents=forms.ModelChoiceField(
                required=False,
                queryset=self.event.subevents,
                empty_label=pgettext_lazy('subevent', 'All dates')
            ),
            start=SplitDateTimeField(
                required=False,
            ),
            end=SplitDateTimeField(
                required=False,
            ),
        )

        kwargs['widget'] = SubeventSelectionWidget(
            event=self.event,
            status_choices=choices,
            subevent_choices=fields.subevents.widget.choices,
        )

        super().__init__(
            fields=fields, require_all_fields=False, *args, **kwargs
        )

    def compress(self, data_list):
        if not data_list:
            return None
        return SubEventSelectionWrapper(data=SubEventSelection(*data_list)).to_string()

    def clean(self, value):
        data = subeventselectionparts(*value)

        if data.selection == "timerange":
            if (data.start != ["", ""] and data.end != ["", ""]) and data.end < data.start:
                raise ValidationError(_("The end date must be after the start date."))

            if (data.start == ["", ""]) and (data.end == ["", ""]):
                raise ValidationError(_('At least one of start and end must be specified.'))

        return super().clean(value)
