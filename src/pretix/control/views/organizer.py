from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from pretix.base.forms import I18nModelForm
from pretix.base.models import Organizer, OrganizerPermission, User
from pretix.base.services.mail import SendMailException, mail
from pretix.control.forms.organizer import OrganizerForm, OrganizerUpdateForm
from pretix.control.permissions import OrganizerPermissionRequiredMixin
from pretix.control.signals import organizer_edit_tabs
from pretix.helpers.urls import build_absolute_uri


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


class OrganizerPermissionForm(I18nModelForm):
    class Meta:
        model = OrganizerPermission
        fields = (
            'can_create_events', 'can_change_permissions'
        )


class OrganizerPermissionCreateForm(OrganizerPermissionForm):
    user = forms.EmailField(required=False, label=_('User'))


class OrganizerDetail(OrganizerPermissionRequiredMixin, DetailView):
    model = Organizer
    template_name = 'pretixcontrol/organizers/detail.html'
    permission = None
    context_object_name = 'organizer'

    def get_object(self, queryset=None) -> Organizer:
        return self.request.organizer

    @cached_property
    def formset(self):
        fs = modelformset_factory(
            OrganizerPermission,
            form=OrganizerPermissionForm,
            can_delete=True, can_order=False, extra=0
        )
        return fs(
            data=(
                self.request.POST
                if self.request.method == "POST" and 'formset-TOTAL_FORMS' in self.request.POST
                else None
            ),
            prefix="formset",
            queryset=OrganizerPermission.objects.filter(organizer=self.request.organizer)
        )

    @cached_property
    def add_form(self):
        return OrganizerPermissionCreateForm(
            data=(
                self.request.POST
                if self.request.method == "POST" and 'formset-TOTAL_FORMS' in self.request.POST
                else None
            ),
            prefix="add"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        ctx['add_form'] = self.add_form
        ctx['events'] = self.request.organizer.events.all()
        ctx['tabs'] = []

        for recv, retv in organizer_edit_tabs.send(sender=self.request.organizer, request=self.request,
                                                   organizer=self.request.organizer):
            ctx['tabs'].append(retv)

        return ctx

    def _send_invite(self, instance):
        try:
            mail(
                instance.invite_email,
                _('Account information changed'),
                'pretixcontrol/email/invitation_organizer.txt',
                {
                    'user': self,
                    'organizer': self.request.organizer.name,
                    'url': build_absolute_uri('control:auth.invite', kwargs={
                        'token': instance.invite_token
                    })
                },
                event=None,
                locale=self.request.LANGUAGE_CODE
            )
        except SendMailException:
            pass  # Already logged

    @transaction.atomic
    def post(self, *args, **kwargs):
        if not self.request.orgaperm.can_change_permissions:
            raise PermissionDenied(_("You have no permission to do this."))

        if 'formset-TOTAL_FORMS' not in self.request.POST:
            return self.get(*args, **kwargs)

        if self.formset.is_valid() and self.add_form.is_valid():
            if self.add_form.has_changed():
                logdata = {
                    k: v for k, v in self.add_form.cleaned_data.items()
                }

                try:
                    self.add_form.instance.organizer = self.request.organizer
                    self.add_form.instance.organizer_id = self.request.organizer.id
                    self.add_form.instance.user = User.objects.get(email=self.add_form.cleaned_data['user'])
                    self.add_form.instance.user_id = self.add_form.instance.user.id
                except User.DoesNotExist:
                    self.add_form.instance.invite_email = self.add_form.cleaned_data['user']
                    if OrganizerPermission.objects.filter(invite_email=self.add_form.instance.invite_email,
                                                          organizer=self.request.organizer).exists():
                        messages.error(self.request, _('This user already has been invited for this team.'))
                        return self.get(*args, **kwargs)

                    self.add_form.save()
                    self._send_invite(self.add_form.instance)

                    self.request.organizer.log_action(
                        'pretix.organizer.permissions.invited', user=self.request.user, data=logdata
                    )
                else:
                    if OrganizerPermission.objects.filter(user=self.add_form.instance.user,
                                                          organizer=self.request.organizer).exists():
                        messages.error(self.request, _('This user already has permissions for this team.'))
                        return self.get(*args, **kwargs)
                    self.add_form.save()
                    logdata['user'] = self.add_form.instance.user_id
                    self.request.organizer.log_action(
                        'pretix.organizer.permissions.added', user=self.request.user, data=logdata
                    )
            for form in self.formset.forms:
                if form.has_changed():
                    changedata = {
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                    changedata['user'] = form.instance.user_id
                    self.request.organizer.log_action(
                        'pretix.organizer.permissions.changed', user=self.request.user, data=changedata
                    )
                if form.instance.user_id == self.request.user.pk:
                    if not form.cleaned_data['can_change_permissions'] or form in self.formset.deleted_forms:
                        messages.error(self.request, _('You cannot remove your own permission to view this page.'))
                        return self.get(*args, **kwargs)

            for form in self.formset.deleted_forms:
                logdata = {
                    k: v for k, v in form.cleaned_data.items()
                }
                self.request.organizer.log_action(
                    'pretix.organizer.permissions.deleted', user=self.request.user, data=logdata
                )

            self.formset.save()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('Your changes could not be saved.'))
            return self.get(*args, **kwargs)

    def get_success_url(self) -> str:
        return reverse('control:organizer', kwargs={
            'organizer': self.request.organizer.slug,
        })


class OrganizerUpdate(OrganizerPermissionRequiredMixin, UpdateView):
    model = Organizer
    form_class = OrganizerUpdateForm
    template_name = 'pretixcontrol/organizers/edit.html'
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
