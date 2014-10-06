from django.shortcuts import render
from django.views.generic.edit import UpdateView
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse

from pytz import common_timezones

from tixlbase.models import Event
from tixlcontrol.permissions import EventPermissionRequiredMixin


class EventUpdateForm(forms.ModelForm):

    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
    )

    def clean_slug(self):
        return self.instance.slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['readonly'] = 'readonly'

    class Meta:
        model = Event
        localized_fields = '__all__'
        fields = [
            'name',
            'slug',
            'locale',
            'timezone',
            'currency',
            'date_from',
            'date_to',
            'show_date_to',
            'show_times',
            'presale_start',
            'presale_end',
            'payment_term_days',
            'payment_term_last',
        ]


class EventUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Event
    form_class = EventUpdateForm
    template_name = 'tixlcontrol/event/settings.html'
    permission = 'can_change_settings'

    def get_object(self, queryset=None):
        return self.request.event

    def get_success_url(self):
        return reverse('control:event.settings', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        }) + '?success=true'


def index(request, organizer, event):
    return render(request, 'tixlcontrol/event/index.html', {})
