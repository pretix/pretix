from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, ListView, TemplateView

from pretix.base.models import Event, EventPermission, OrganizerPermission
from pretix.control.forms.event import EventCreateForm
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


def index(request):
    return render(request, 'pretixcontrol/dashboard.html', {})


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

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

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
        return ret

    def get_success_url(self) -> str:
        return reverse('control:event.settings', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.object.slug,
        })
