from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView

from pretix.base.models import Organizer, OrganizerPermission
from pretix.control.forms.organizer import OrganizerForm, OrganizerUpdateForm
from pretix.control.permissions import OrganizerPermissionRequiredMixin


class OrganizerList(ListView):
    model = Organizer
    context_object_name = 'organizers'
    template_name = 'pretixcontrol/organizers/index.html'
    paginate_by = 30

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Organizer.objects.all()
        else:
            return Organizer.objects.filter(
                permitted__id__exact=self.request.user.pk
            )


class OrganizerUpdate(OrganizerPermissionRequiredMixin, UpdateView):
    model = Organizer
    form_class = OrganizerUpdateForm
    template_name = 'pretixcontrol/organizers/detail.html'
    permission = None
    context_object_name = 'organizer'

    def get_object(self, queryset=None) -> Organizer:
        return self.request.organizer

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:organizer.edit', kwargs={
            'organizer': self.request.organizer.slug,
        })


class OrganizerCreate(CreateView):
    model = Organizer
    form_class = OrganizerForm
    template_name = 'pretixcontrol/organizers/create.html'
    context_object_name = 'organizer'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied()  # TODO
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, _('The new organizer has been created.'))
        ret = super().form_valid(form)
        OrganizerPermission.objects.create(
            organizer=form.instance, user=self.request.user,
            can_create_events=True
        )
        return ret

    def get_success_url(self) -> str:
        return reverse('control:organizers')
