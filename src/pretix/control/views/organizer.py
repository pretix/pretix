from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Count
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView,
)

from pretix.base.forms import I18nModelForm
from pretix.base.models import Organizer, OrganizerPermission, Team, User
from pretix.base.services.mail import SendMailException, mail
from pretix.control.forms.organizer import (
    OrganizerForm, OrganizerUpdateForm, TeamForm,
)
from pretix.control.permissions import OrganizerPermissionRequiredMixin
from pretix.control.signals import nav_organizer
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


class OrganizerDetailViewMixin:

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_organizer'] = []
        ctx['organizer'] = self.request.organizer

        for recv, retv in nav_organizer.send(sender=self.request.organizer, request=self.request,
                                             organizer=self.request.organizer):
            ctx['nav_organizer'] += retv
        return ctx

    def get_object(self, queryset=None) -> Organizer:
        return self.request.organizer


class OrganizerDetail(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = Organizer
    template_name = 'pretixcontrol/organizers/detail.html'
    permission = None
    context_object_name = 'organizer'

    def get_object(self, queryset=None) -> Organizer:
        return self.request.organizer

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['events'] = self.request.organizer.events.all()
        return ctx


class OrganizerTeamView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = Organizer
    template_name = 'pretixcontrol/organizers/teams.html'
    permission = 'can_change_permissions'
    context_object_name = 'organizer'

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
        return ctx

    def _send_invite(self, instance):
        try:
            mail(
                instance.invite_email,
                _('pretix account invitation'),
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
        return reverse('control:organizer.teams', kwargs={
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.is_superuser:
            kwargs['domain'] = True
        return kwargs

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


class TeamListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = Team
    template_name = 'pretixcontrol/organizers/teams.html'
    permission = 'can_change_teams'
    context_object_name = 'teams'

    def get_queryset(self):
        return self.request.organizer.teams.annotate(
            memcount=Count('members', distinct=True),
            eventcount=Count('limit_events', distinct=True),
            invcount=Count('invites', distinct=True)
        ).all()


class TeamCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = Team
    template_name = 'pretixcontrol/organizers/team_edit.html'
    permission = 'can_change_teams'
    form_class = TeamForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Team, organizer=self.request.organizer, pk=self.kwargs.get('team'))

    def get_success_url(self):
        return reverse('control:organizer.team.edit', kwargs={
            'organizer': self.request.organizer.slug,
            'team': self.object.pk
        })

    def form_valid(self, form):
        messages.success(self.request, _('The team has been created. You can now add members to the team.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.team.created', user=self.request.user, data={
            k: getattr(self.object, k) if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
            for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class TeamUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = Team
    template_name = 'pretixcontrol/organizers/team_edit.html'
    permission = 'can_change_teams'
    context_object_name = 'team'
    form_class = TeamForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Team, organizer=self.request.organizer, pk=self.kwargs.get('team'))

    def get_success_url(self):
        return reverse('control:organizer.team.edit', kwargs={
            'organizer': self.request.organizer.slug,
            'team': self.object.pk
        })

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.team.changed', user=self.request.user, data={
                k: getattr(self.object, k) if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class TeamDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DeleteView):
    model = Team
    template_name = 'pretixcontrol/organizers/team_delete.html'
    permission = 'can_change_teams'
    context_object_name = 'team'

    def get_object(self, queryset=None):
        return get_object_or_404(Team, organizer=self.request.organizer, pk=self.kwargs.get('team'))

    def get_success_url(self):
        return reverse('control:organizer.teams', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.is_allowed()
        return context

    def is_allowed(self) -> bool:
        return self.request.organizer.teams.exclude(pk=self.kwargs.get('team')).filter(
            can_change_teams=True, members__isnull=False
        ).exists()

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        if self.is_allowed():
            self.object.log_action('pretix.team.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected team has been deleted.'))
            return redirect(success_url)
        else:
            messages.error(request, _('The selected cannot be deleted.'))
            return redirect(success_url)


class TeamMemberView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    template_name = 'pretixcontrol/organizers/team_members.html'
    context_object_name = 'team'
    permission = 'can_change_teams'
    model = Team

    def get_object(self, queryset=None):
        return get_object_or_404(Team, organizer=self.request.organizer, pk=self.kwargs.get('team'))
