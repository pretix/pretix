from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, ListView, TemplateView

from pretix.base.models import Event, EventPermission, OrganizerPermission
from pretix.control.forms.event import (
    EventCreateForm, EventCreateSettingsForm, EventSettingsForm,
)
from pretix.control.permissions import OrganizerPermissionRequiredMixin


class EventList(ListView):
    model = Event
    context_object_name = 'events'
    paginate_by = 30
    template_name = 'pretixcontrol/events/index.html'

    def get_queryset(self):
        return Event.objects.filter(
            permitted__id__exact=self.request.user.pk
        ).prefetch_related(
            "organizer",
        )


class EventCreateStart(TemplateView):
    template_name = 'pretixcontrol/events/start.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['organizers'] = [
            p.organizer for p in OrganizerPermission.objects.filter(
                user=self.request.user, can_create_events=True
            ).select_related("organizer")
        ]
        return ctx


class EventCreate(OrganizerPermissionRequiredMixin, CreateView):
    model = Event
    form_class = EventCreateForm
    template_name = 'pretixcontrol/events/create.html'
    context_object_name = 'event'
    permission = 'can_create_events'

    @cached_property
    def sform(self):
        return EventCreateSettingsForm(
            obj=Event(),
            prefix='settings',
            data=self.request.POST if self.request.method == 'POST' else None
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid() and self.sform.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['sform'] = self.sform
        return context

    def dispatch(self, request, *args, **kwargs):
        self.object = Event()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('The new event has been created.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        EventPermission.objects.create(
            event=form.instance, user=self.request.user,
        )
        self.object = form.instance
        self.object.plugins = settings.PRETIX_PLUGINS_DEFAULT
        self.object.save()

        self.sform.obj = form.instance
        self.sform.save()
        form.instance.log_action('pretix.event.settings', user=self.request.user, data={
            k: form.instance.settings.get(k) for k in self.sform.changed_data
        })
        return ret

    def get_success_url(self) -> str:
        return reverse('control:event.settings', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.object.slug,
        })
