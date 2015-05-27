from django import forms
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseForbidden
from django.utils.translation import ugettext_lazy as _
from django.views.generic import ListView, UpdateView, CreateView
from pretix.base.forms import VersionedModelForm

from pretix.base.models import Organizer, OrganizerPermission
from pretix.control.permissions import OrganizerPermissionRequiredMixin


class OrganizerList(ListView):
    model = Organizer
    context_object_name = 'organizers'
    template_name = 'pretixcontrol/organizers/index.html'
    paginate_by = 30

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Organizer.objects.current.all()
        else:
            return Organizer.objects.current.filter(
                permitted__id__exact=self.request.user.pk
            )


class OrganizerForm(VersionedModelForm):
    error_messages = {
        'duplicate_slug': _("This slug is already in use. Please choose a different one."),
    }

    class Meta:
        model = Organizer
        fields = ['name', 'slug']

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if Organizer.objects.filter(slug=slug).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug',
            )
        return slug


class OrganizerUpdateForm(OrganizerForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['disabled'] = 'disabled'

    def clean_slug(self):
        return self.instance.slug


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
            return HttpResponseForbidden()  # TODO
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
