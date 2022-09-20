from datetime import datetime, timedelta
from urllib.parse import urlencode

from django import forms
from django.forms import formset_factory, ModelForm
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.dates import MONTHS, WEEKDAYS
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from i18nfield.forms import I18nInlineFormSet

from pretix.base.forms import I18nModelForm
from pretix.base.forms.widgets import DatePickerWidget, TimePickerWidget
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models import WaitingListEntry
from pretix.base.models.items import SubEventItem, SubEventItemVariation
from pretix.base.reldate import RelativeDateTimeField, RelativeDateWrapper
from pretix.base.templatetags.money import money_filter
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.helpers.money import change_decimal_field
from django_scopes import scopes_disabled

with scopes_disabled():
    class WaitingListEntryEditForm(I18nModelForm):

        def __init__(self, *args, **kwargs):
            self.event = kwargs['event']
            super().__init__(*args, **kwargs)
            self.fields['subevent'].queryset = self.event.subevents.all()

        class Meta:
            model = WaitingListEntry
            localized_fields = '__all__'
            fields = [
                'subevent',
            ]
            field_classes = {
            }
            widgets = {
            }


