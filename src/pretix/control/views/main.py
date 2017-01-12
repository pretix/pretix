from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView
from formtools.wizard.views import SessionWizardView

from pretix.base.models import Event, EventPermission, OrganizerPermission
from pretix.control.forms.event import (
    EventWizardBasicsForm, EventWizardCopyForm, EventWizardFoundationForm,
)


class EventList(ListView):
    model = Event
    context_object_name = 'events'
    paginate_by = 30
    template_name = 'pretixcontrol/events/index.html'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Event.objects.all().select_related("organizer").prefetch_related(
                "setting_objects", "organizer__setting_objects"
            )
        else:
            return Event.objects.filter(
                permitted__id__exact=self.request.user.pk
            ).select_related("organizer").prefetch_related(
                "setting_objects", "organizer__setting_objects"
            )


def condition_copy(wizard):
    return EventPermission.objects.filter(
        user=wizard.request.user, can_change_settings=True, can_change_items=True
    ).exists()


class EventWizard(SessionWizardView):
    form_list = [
        ('foundation', EventWizardFoundationForm),
        ('basics', EventWizardBasicsForm),
        ('copy', EventWizardCopyForm),
    ]
    templates = {
        'foundation': 'pretixcontrol/events/create_foundation.html',
        'basics': 'pretixcontrol/events/create_basics.html',
        'copy': 'pretixcontrol/events/create_copy.html',
    }
    condition_dict = {
        'copy': condition_copy
    }

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['has_organizer'] = OrganizerPermission.objects.filter(user=self.request.user,
                                                                  can_create_events=True).exists()
        return ctx

    def get_form_kwargs(self, step=None):
        kwargs = {
            'user': self.request.user
        }
        if step != 'foundation':
            fdata = self.get_cleaned_data_for_step('foundation')
            kwargs.update(fdata)
        return kwargs

    def get_template_names(self):
        return [self.templates[self.steps.current]]

    def done(self, form_list, form_dict, **kwargs):
        foundation_data = self.get_cleaned_data_for_step('foundation')
        basics_data = self.get_cleaned_data_for_step('basics')
        copy_data = self.get_cleaned_data_for_step('copy')

        with transaction.atomic():
            event = form_dict['basics'].instance
            event.organizer = foundation_data['organizer']
            event.plugins = settings.PRETIX_PLUGINS_DEFAULT
            form_dict['basics'].save()
            EventPermission.objects.create(event=event, user=self.request.user)

            logdata = {}
            for f in form_list:
                logdata.update({
                    k: v for k, v in f.cleaned_data.items()
                })
            event.log_action('pretix.event.settings', user=self.request.user, data=logdata)

            if copy_data and copy_data['copy_from_event']:
                from_event = copy_data['copy_from_event']
                event.copy_data_from(from_event)

            event.settings.set('timezone', basics_data['timezone'])
            event.settings.set('locale', basics_data['locale'])
            event.settings.set('locales', foundation_data['locales'])

        messages.success(self.request, _('The new event has been created. You can now adjust the event settings in '
                                         'detail.'))
        return redirect(reverse('control:event.settings', kwargs={
            'organizer': event.organizer.slug,
            'event': event.slug,
        }))
