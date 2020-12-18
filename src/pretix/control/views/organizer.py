import json
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import (
    Count, Max, Min, OuterRef, Prefetch, ProtectedError, Subquery, Sum,
)
from django.db.models.functions import Coalesce, Greatest
from django.forms import DecimalField, inlineformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, DetailView, FormView, ListView, TemplateView,
    UpdateView,
)

from pretix.api.models import WebHook
from pretix.base.auth import get_auth_backends
from pretix.base.models import (
    CachedFile, Device, Gate, GiftCard, LogEntry, OrderPayment, Organizer,
    Team, TeamInvite, User,
)
from pretix.base.models.event import Event, EventMetaProperty, EventMetaValue
from pretix.base.models.giftcards import (
    GiftCardTransaction, gen_giftcard_secret,
)
from pretix.base.models.organizer import TeamAPIToken
from pretix.base.payment import PaymentException
from pretix.base.services.export import multiexport
from pretix.base.services.mail import SendMailException, mail
from pretix.base.signals import register_multievent_data_exporters
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.filter import (
    EventFilterForm, GiftCardFilterForm, OrganizerFilterForm,
)
from pretix.control.forms.orders import ExporterForm
from pretix.control.forms.organizer import (
    DeviceForm, EventMetaPropertyForm, GateForm, GiftCardCreateForm,
    GiftCardUpdateForm, OrganizerDeleteForm, OrganizerForm,
    OrganizerSettingsForm, OrganizerUpdateForm, TeamForm, WebHookForm,
)
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, OrganizerPermissionRequiredMixin,
)
from pretix.control.signals import nav_organizer
from pretix.control.views import PaginationMixin
from pretix.helpers.dicts import merge_dicts
from pretix.helpers.urls import build_absolute_uri
from pretix.presale.style import regenerate_organizer_css


class OrganizerList(PaginationMixin, ListView):
    model = Organizer
    context_object_name = 'organizers'
    template_name = 'pretixcontrol/organizers/index.html'

    def get_queryset(self):
        qs = Organizer.objects.all()
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        if self.request.user.has_active_staff_session(self.request.session.session_key):
            return qs
        else:
            return qs.filter(pk__in=self.request.user.teams.values_list('organizer', flat=True))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return OrganizerFilterForm(data=self.request.GET, request=self.request)


class InviteForm(forms.Form):
    user = forms.EmailField(required=False, label=_('User'))


class TokenForm(forms.Form):
    name = forms.CharField(required=False, label=_('Token name'))


class OrganizerDetailViewMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav_organizer'] = []
        ctx['organizer'] = self.request.organizer

        for recv, retv in nav_organizer.send(sender=self.request.organizer, request=self.request,
                                             organizer=self.request.organizer):
            ctx['nav_organizer'] += retv
        ctx['nav_organizer'].sort(key=lambda n: n['label'])
        return ctx

    def get_object(self, queryset=None) -> Organizer:
        return self.request.organizer


class OrganizerDetail(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = Event
    template_name = 'pretixcontrol/organizers/detail.html'
    permission = None
    context_object_name = 'events'
    paginate_by = 50

    @property
    def organizer(self):
        return self.request.organizer

    def get_queryset(self):
        qs = self.request.user.get_events_with_any_permission(self.request).select_related('organizer').prefetch_related(
            'organizer', '_settings_objects', 'organizer___settings_objects',
            'organizer__meta_properties',
            Prefetch(
                'meta_values',
                EventMetaValue.objects.select_related('property'),
                to_attr='meta_values_cached'
            )
        ).filter(organizer=self.request.organizer).order_by('-date_from')
        qs = qs.annotate(
            min_from=Min('subevents__date_from'),
            max_from=Max('subevents__date_from'),
            max_to=Max('subevents__date_to'),
            max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from'))
        ).annotate(
            order_from=Coalesce('min_from', 'date_from'),
            order_to=Coalesce('max_fromto', 'max_to', 'max_from', 'date_to', 'date_from'),
        )
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    @cached_property
    def filter_form(self):
        return EventFilterForm(data=self.request.GET, request=self.request, organizer=self.organizer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        ctx['meta_fields'] = [
            self.filter_form['meta_{}'.format(p.name)] for p in self.organizer.meta_properties.all()
        ]
        return ctx


class OrganizerTeamView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = Organizer
    template_name = 'pretixcontrol/organizers/teams.html'
    permission = 'can_change_permissions'
    context_object_name = 'organizer'


class OrganizerSettingsFormView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, FormView):
    model = Organizer
    permission = 'can_change_organizer_settings'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['obj'] = self.request.organizer
        return kwargs

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.organizer.log_action(
                    'pretix.organizer.settings', user=self.request.user, data={
                        k: (form.cleaned_data.get(k).name
                            if isinstance(form.cleaned_data.get(k), File)
                            else form.cleaned_data.get(k))
                        for k in form.changed_data
                    }
                )
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)


class OrganizerDisplaySettings(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, View):
    permission = None

    def get(self, request, *wargs, **kwargs):
        return redirect(reverse('control:organizer.edit', kwargs={
            'organizer': self.request.organizer.slug,
        }) + '#tab-0-3-open')


class OrganizerDelete(AdministratorPermissionRequiredMixin, FormView):
    model = Organizer
    template_name = 'pretixcontrol/organizers/delete.html'
    context_object_name = 'organizer'
    form_class = OrganizerDeleteForm

    def post(self, request, *args, **kwargs):
        if not self.request.organizer.allow_delete():
            messages.error(self.request, _('This organizer can not be deleted.'))
            return self.get(self.request, *self.args, **self.kwargs)
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.request.user.log_action(
                    'pretix.organizer.deleted', user=self.request.user,
                    data={
                        'organizer_id': self.request.organizer.pk,
                        'name': str(self.request.organizer.name),
                        'logentries': list(self.request.organizer.all_logentries().values_list('pk', flat=True))
                    }
                )
                self.request.organizer.delete_sub_objects()
                self.request.organizer.delete()
            messages.success(self.request, _('The organizer has been deleted.'))
            return redirect(self.get_success_url())
        except ProtectedError:
            messages.error(self.request, _('The organizer could not be deleted as some constraints (e.g. data created by '
                                           'plug-ins) do not allow it.'))
            return self.get(self.request, *self.args, **self.kwargs)

    def get_success_url(self) -> str:
        return reverse('control:index')


class OrganizerUpdate(OrganizerPermissionRequiredMixin, UpdateView):
    model = Organizer
    form_class = OrganizerUpdateForm
    template_name = 'pretixcontrol/organizers/edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'organizer'

    @cached_property
    def object(self) -> Organizer:
        return self.request.organizer

    def get_object(self, queryset=None) -> Organizer:
        return self.object

    @cached_property
    def sform(self):
        return OrganizerSettingsForm(
            obj=self.object,
            prefix='settings',
            data=self.request.POST if self.request.method == 'POST' else None,
            files=self.request.FILES if self.request.method == 'POST' else None
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['sform'] = self.sform
        context['formset'] = self.formset
        return context

    @transaction.atomic
    def form_valid(self, form):
        self.save_formset(self.object)
        self.sform.save()
        change_css = False
        if self.sform.has_changed():
            self.request.organizer.log_action(
                'pretix.organizer.settings',
                user=self.request.user,
                data={
                    k: (self.sform.cleaned_data.get(k).name
                        if isinstance(self.sform.cleaned_data.get(k), File)
                        else self.sform.cleaned_data.get(k))
                    for k in self.sform.changed_data
                }
            )
            display_properties = (
                'primary_color', 'theme_color_success', 'theme_color_danger', 'primary_font',
                'theme_color_background', 'theme_round_borders'
            )
            if any(p in self.sform.changed_data for p in display_properties):
                change_css = True
        if form.has_changed():
            self.request.organizer.log_action(
                'pretix.organizer.changed',
                user=self.request.user,
                data={k: form.cleaned_data.get(k) for k in form.changed_data}
            )

        if change_css:
            regenerate_organizer_css.apply_async(args=(self.request.organizer.pk,))
            messages.success(self.request, _('Your changes have been saved. Please note that it can '
                                             'take a short period of time until your changes become '
                                             'active.'))
        else:
            messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.has_active_staff_session(self.request.session.session_key):
            kwargs['domain'] = True
            kwargs['change_slug'] = True
        return kwargs

    def get_success_url(self) -> str:
        return reverse('control:organizer.edit', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid() and self.sform.is_valid() and self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @cached_property
    def formset(self):
        formsetclass = inlineformset_factory(
            Organizer, EventMetaProperty,
            form=EventMetaPropertyForm, can_order=False, can_delete=True, extra=0
        )
        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            instance=self.object, queryset=self.object.meta_properties.all())

    def save_formset(self, obj):
        for form in self.formset.initial_forms:
            if form in self.formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.save()

        for form in self.formset.extra_forms:
            if not form.has_changed():
                continue
            if self.formset._should_delete_form(form):
                continue
            form.instance.organizer = obj
            form.save()


class OrganizerCreate(CreateView):
    model = Organizer
    form_class = OrganizerForm
    template_name = 'pretixcontrol/organizers/create.html'
    context_object_name = 'organizer'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_active_staff_session(self.request.session.session_key):
            raise PermissionDenied()  # TODO
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('The new organizer has been created.'))
        ret = super().form_valid(form)
        t = Team.objects.create(
            organizer=form.instance, name=_('Administrators'),
            all_events=True, can_create_events=True, can_change_teams=True, can_manage_gift_cards=True,
            can_change_organizer_settings=True, can_change_event_settings=True, can_change_items=True,
            can_view_orders=True, can_change_orders=True, can_view_vouchers=True, can_change_vouchers=True
        )
        t.members.add(self.request.user)
        return ret

    def get_success_url(self) -> str:
        return reverse('control:organizer', kwargs={
            'organizer': self.object.slug,
        })


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
        return reverse('control:organizer.team', kwargs={
            'organizer': self.request.organizer.slug,
            'team': self.object.pk
        })

    def form_valid(self, form):
        messages.success(self.request, _('The team has been created. You can now add members to the team.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.members.add(self.request.user)
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
        return reverse('control:organizer.team', kwargs={
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
            messages.error(request, _('The selected team cannot be deleted.'))
            return redirect(success_url)


class TeamMemberView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    template_name = 'pretixcontrol/organizers/team_members.html'
    context_object_name = 'team'
    permission = 'can_change_teams'
    model = Team

    def get_object(self, queryset=None):
        return get_object_or_404(Team, organizer=self.request.organizer, pk=self.kwargs.get('team'))

    @cached_property
    def add_form(self):
        return InviteForm(data=(self.request.POST
                                if self.request.method == "POST" and "user" in self.request.POST else None))

    @cached_property
    def add_token_form(self):
        return TokenForm(data=(self.request.POST
                               if self.request.method == "POST" and "name" in self.request.POST else None))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['add_form'] = self.add_form
        ctx['add_token_form'] = self.add_token_form
        return ctx

    def _send_invite(self, instance):
        try:
            mail(
                instance.email,
                _('pretix account invitation'),
                'pretixcontrol/email/invitation.txt',
                {
                    'user': self,
                    'organizer': self.request.organizer.name,
                    'team': instance.team.name,
                    'url': build_absolute_uri('control:auth.invite', kwargs={
                        'token': instance.token
                    })
                },
                event=None,
                locale=self.request.LANGUAGE_CODE
            )
        except SendMailException:
            pass  # Already logged

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if 'remove-member' in request.POST:
            try:
                user = User.objects.get(pk=request.POST.get('remove-member'))
            except (User.DoesNotExist, ValueError):
                pass
            else:
                other_admin_teams = self.request.organizer.teams.exclude(pk=self.object.pk).filter(
                    can_change_teams=True, members__isnull=False
                ).exists()
                if not other_admin_teams and self.object.can_change_teams and self.object.members.count() == 1:
                    messages.error(self.request, _('You cannot remove the last member from this team as no one would '
                                                   'be left with the permission to change teams.'))
                    return redirect(self.get_success_url())
                else:
                    self.object.members.remove(user)
                    self.object.log_action(
                        'pretix.team.member.removed', user=self.request.user, data={
                            'email': user.email,
                            'user': user.pk
                        }
                    )
                    messages.success(self.request, _('The member has been removed from the team.'))
                    return redirect(self.get_success_url())

        elif 'remove-invite' in request.POST:
            try:
                invite = self.object.invites.get(pk=request.POST.get('remove-invite'))
            except (TeamInvite.DoesNotExist, ValueError):
                messages.error(self.request, _('Invalid invite selected.'))
                return redirect(self.get_success_url())
            else:
                invite.delete()
                self.object.log_action(
                    'pretix.team.invite.deleted', user=self.request.user, data={
                        'email': invite.email
                    }
                )
                messages.success(self.request, _('The invite has been revoked.'))
                return redirect(self.get_success_url())

        elif 'resend-invite' in request.POST:
            try:
                invite = self.object.invites.get(pk=request.POST.get('resend-invite'))
            except (TeamInvite.DoesNotExist, ValueError):
                messages.error(self.request, _('Invalid invite selected.'))
                return redirect(self.get_success_url())
            else:
                self._send_invite(invite)
                self.object.log_action(
                    'pretix.team.invite.resent', user=self.request.user, data={
                        'email': invite.email
                    }
                )
                messages.success(self.request, _('The invite has been resent.'))
                return redirect(self.get_success_url())

        elif 'remove-token' in request.POST:
            try:
                token = self.object.tokens.get(pk=request.POST.get('remove-token'))
            except (TeamAPIToken.DoesNotExist, ValueError):
                messages.error(self.request, _('Invalid token selected.'))
                return redirect(self.get_success_url())
            else:
                token.active = False
                token.save()
                self.object.log_action(
                    'pretix.team.token.deleted', user=self.request.user, data={
                        'name': token.name
                    }
                )
                messages.success(self.request, _('The token has been revoked.'))
                return redirect(self.get_success_url())

        elif "user" in self.request.POST and self.add_form.is_valid() and self.add_form.has_changed():

            try:
                user = User.objects.get(email__iexact=self.add_form.cleaned_data['user'])
            except User.DoesNotExist:
                if self.object.invites.filter(email__iexact=self.add_form.cleaned_data['user']).exists():
                    messages.error(self.request, _('This user already has been invited for this team.'))
                    return self.get(request, *args, **kwargs)
                if 'native' not in get_auth_backends():
                    messages.error(self.request, _('Users need to have a pretix account before they can be invited.'))
                    return self.get(request, *args, **kwargs)

                invite = self.object.invites.create(email=self.add_form.cleaned_data['user'])
                self._send_invite(invite)
                self.object.log_action(
                    'pretix.team.invite.created', user=self.request.user, data={
                        'email': self.add_form.cleaned_data['user']
                    }
                )
                messages.success(self.request, _('The new member has been invited to the team.'))
                return redirect(self.get_success_url())
            else:
                if self.object.members.filter(pk=user.pk).exists():
                    messages.error(self.request, _('This user already has permissions for this team.'))
                    return self.get(request, *args, **kwargs)

                self.object.members.add(user)
                self.object.log_action(
                    'pretix.team.member.added', user=self.request.user,
                    data={
                        'email': user.email,
                        'user': user.pk,
                    }
                )
                messages.success(self.request, _('The new member has been added to the team.'))
                return redirect(self.get_success_url())

        elif "name" in self.request.POST and self.add_token_form.is_valid() and self.add_token_form.has_changed():
            token = self.object.tokens.create(name=self.add_token_form.cleaned_data['name'])
            self.object.log_action(
                'pretix.team.token.created', user=self.request.user, data={
                    'name': self.add_token_form.cleaned_data['name'],
                    'id': token.pk
                }
            )
            messages.success(self.request, _('A new API token has been created with the following secret: {}\n'
                                             'Please copy this secret to a safe place. You will not be able to '
                                             'view it again here.').format(token.token))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('Your changes could not be saved.'))
            return self.get(request, *args, **kwargs)

    def get_success_url(self) -> str:
        return reverse('control:organizer.team', kwargs={
            'organizer': self.request.organizer.slug,
            'team': self.object.pk
        })


class DeviceListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = Device
    template_name = 'pretixcontrol/organizers/devices.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'devices'

    def get_queryset(self):
        return self.request.organizer.devices.prefetch_related(
            'limit_events'
        ).order_by('revoked', '-device_id')


class DeviceCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = Device
    template_name = 'pretixcontrol/organizers/device_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = DeviceForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_success_url(self):
        return reverse('control:organizer.device.connect', kwargs={
            'organizer': self.request.organizer.slug,
            'device': self.object.pk
        })

    def form_valid(self, form):
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.device.created', user=self.request.user, data={
            k: getattr(self.object, k) if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
            for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class DeviceLogView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    template_name = 'pretixcontrol/organizers/device_logs.html'
    permission = 'can_change_organizer_settings'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 20

    @cached_property
    def device(self):
        return get_object_or_404(Device, organizer=self.request.organizer, pk=self.kwargs.get('device'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['device'] = self.device
        return ctx

    def get_queryset(self):
        qs = LogEntry.objects.filter(
            device_id=self.device
        ).select_related(
            'user', 'content_type', 'api_token', 'oauth_application',
        ).prefetch_related(
            'device', 'event'
        ).order_by('-datetime')
        return qs


class DeviceUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = Device
    template_name = 'pretixcontrol/organizers/device_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'device'
    form_class = DeviceForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Device, organizer=self.request.organizer, pk=self.kwargs.get('device'))

    def get_success_url(self):
        return reverse('control:organizer.devices', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.device.changed', user=self.request.user, data={
                k: getattr(self.object, k) if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class DeviceConnectView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = Device
    template_name = 'pretixcontrol/organizers/device_connect.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'device'

    def get_object(self, queryset=None):
        return get_object_or_404(Device, organizer=self.request.organizer, pk=self.kwargs.get('device'))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if 'ajax' in request.GET:
            return JsonResponse({
                'initialized': bool(self.object.initialized)
            })
        if self.object.initialized:
            messages.success(request, _('This device has been set up successfully.'))
            return redirect(reverse('control:organizer.devices', kwargs={
                'organizer': self.request.organizer.slug,
            }))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['qrdata'] = json.dumps({
            'handshake_version': 1,
            'url': settings.SITE_URL,
            'token': self.object.initialization_token,
        })
        return ctx


class DeviceRevokeView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    model = Device
    template_name = 'pretixcontrol/organizers/device_revoke.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'device'

    def get_object(self, queryset=None):
        return get_object_or_404(Device, organizer=self.request.organizer, pk=self.kwargs.get('device'))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.api_token:
            messages.success(request, _('This device currently does not have access.'))
            return redirect(reverse('control:organizer.devices', kwargs={
                'organizer': self.request.organizer.slug,
            }))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.revoked = True
        self.object.save()
        self.object.log_action('pretix.device.revoked', user=self.request.user)
        messages.success(request, _('Access for this device has been revoked.'))
        return redirect(reverse('control:organizer.devices', kwargs={
            'organizer': self.request.organizer.slug,
        }))


class WebHookListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = WebHook
    template_name = 'pretixcontrol/organizers/webhooks.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'webhooks'

    def get_queryset(self):
        return self.request.organizer.webhooks.prefetch_related('limit_events')


class WebHookCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = WebHook
    template_name = 'pretixcontrol/organizers/webhook_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = WebHookForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_success_url(self):
        return reverse('control:organizer.webhooks', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        self.request.organizer.log_action('pretix.webhook.created', user=self.request.user, data=merge_dicts({
            k: form.cleaned_data[k] if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
            for k in form.changed_data
        }, {'id': form.instance.pk}))
        new_listeners = set(form.cleaned_data['events'])
        for l in new_listeners:
            self.object.listeners.create(action_type=l)
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class WebHookUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = WebHook
    template_name = 'pretixcontrol/organizers/webhook_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'webhook'
    form_class = WebHookForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(WebHook, organizer=self.request.organizer, pk=self.kwargs.get('webhook'))

    def get_success_url(self):
        return reverse('control:organizer.webhooks', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        if form.has_changed():
            self.request.organizer.log_action('pretix.webhook.changed', user=self.request.user, data=merge_dicts({
                k: form.cleaned_data[k] if k != 'limit_events' else [e.id for e in getattr(self.object, k).all()]
                for k in form.changed_data
            }, {'id': form.instance.pk}))

        current_listeners = set(self.object.listeners.values_list('action_type', flat=True))
        new_listeners = set(form.cleaned_data['events'])
        for l in current_listeners - new_listeners:
            self.object.listeners.filter(action_type=l).delete()
        for l in new_listeners - current_listeners:
            self.object.listeners.create(action_type=l)

        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class WebHookLogsView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = WebHook
    template_name = 'pretixcontrol/organizers/webhook_logs.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'calls'
    paginate_by = 50

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['webhook'] = self.webhook
        return ctx

    @cached_property
    def webhook(self):
        return get_object_or_404(
            WebHook, organizer=self.request.organizer, pk=self.kwargs.get('webhook')
        )

    def get_queryset(self):
        return self.webhook.calls.order_by('-datetime')


class GiftCardListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = GiftCard
    template_name = 'pretixcontrol/organizers/giftcards.html'
    permission = 'can_manage_gift_cards'
    context_object_name = 'giftcards'

    def get_queryset(self):
        s = GiftCardTransaction.objects.filter(
            card=OuterRef('pk')
        ).order_by().values('card').annotate(s=Sum('value')).values('s')
        qs = self.request.organizer.issued_gift_cards.annotate(
            cached_value=Coalesce(Subquery(s), Decimal('0.00'))
        ).order_by('-issuance')
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def post(self, request, *args, **kwargs):
        if "add" in request.POST:
            o = self.request.user.get_organizers_with_permission(
                'can_manage_gift_cards', self.request
            ).exclude(pk=self.request.organizer.pk).filter(
                slug=request.POST.get("add")
            ).first()
            if o:
                self.request.organizer.gift_card_issuer_acceptance.get_or_create(
                    issuer=o
                )
                self.request.organizer.log_action(
                    'pretix.giftcards.acceptance.added',
                    data={'issuer': o.slug},
                    user=request.user
                )
                messages.success(self.request, _('The selected gift card issuer has been added.'))
        if "del" in request.POST:
            o = Organizer.objects.filter(
                slug=request.POST.get("del")
            ).first()
            if o:
                self.request.organizer.gift_card_issuer_acceptance.filter(
                    issuer=o
                ).delete()
                self.request.organizer.log_action(
                    'pretix.giftcards.acceptance.removed',
                    data={'issuer': o.slug},
                    user=request.user
                )
                messages.success(self.request, _('The selected gift card issuer has been removed.'))
        return redirect(reverse('control:organizer.giftcards', kwargs={'organizer': self.request.organizer.slug}))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        ctx['other_organizers'] = self.request.user.get_organizers_with_permission(
            'can_manage_gift_cards', self.request
        ).exclude(pk=self.request.organizer.pk)
        return ctx

    @cached_property
    def filter_form(self):
        return GiftCardFilterForm(data=self.request.GET, request=self.request)


class GiftCardDetailView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    template_name = 'pretixcontrol/organizers/giftcard.html'
    permission = 'can_manage_gift_cards'
    context_object_name = 'card'

    def get_object(self, queryset=None) -> Organizer:
        return get_object_or_404(
            self.request.organizer.issued_gift_cards,
            pk=self.kwargs.get('giftcard')
        )

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        self.object = GiftCard.objects.select_for_update().get(pk=self.get_object().pk)
        if 'revert' in request.POST:
            t = get_object_or_404(self.object.transactions.all(), pk=request.POST.get('revert'), order__isnull=False)
            if self.object.value - t.value < Decimal('0.00'):
                messages.error(request, _('Gift cards are not allowed to have negative values.'))
            elif t.value > 0:
                r = t.order.payments.create(
                    order=t.order,
                    state=OrderPayment.PAYMENT_STATE_CREATED,
                    amount=t.value,
                    provider='giftcard',
                    info=json.dumps({
                        'gift_card': self.object.pk,
                        'retry': True,
                    })
                )
                try:
                    r.payment_provider.execute_payment(request, r)
                except PaymentException as e:
                    with transaction.atomic():
                        r.state = OrderPayment.PAYMENT_STATE_FAILED
                        r.save()
                        t.order.log_action('pretix.event.order.payment.failed', {
                            'local_id': r.local_id,
                            'provider': r.provider,
                            'error': str(e)
                        })
                    messages.error(request, _('The transaction could not be reversed.'))
                else:
                    messages.success(request, _('The transaction has been reversed.'))
        elif 'value' in request.POST:
            try:
                value = DecimalField(localize=True).to_python(request.POST.get('value'))
            except ValidationError:
                messages.error(request, _('Your input was invalid, please try again.'))
            else:
                if self.object.value + value < Decimal('0.00'):
                    messages.error(request, _('Gift cards are not allowed to have negative values.'))
                else:
                    self.object.transactions.create(
                        value=value,
                        text=request.POST.get('text') or None,
                    )
                    self.object.log_action(
                        'pretix.giftcards.transaction.manual',
                        data={
                            'value': value,
                            'text': request.POST.get('text')
                        },
                        user=self.request.user,
                    )
                    messages.success(request, _('The manual transaction has been saved.'))
                    return redirect(reverse(
                        'control:organizer.giftcard',
                        kwargs={
                            'organizer': request.organizer.slug,
                            'giftcard': self.object.pk
                        }
                    ))
        return self.get(request, *args, **kwargs)


class GiftCardCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    template_name = 'pretixcontrol/organizers/giftcard_create.html'
    permission = 'can_manage_gift_cards'
    form_class = GiftCardCreateForm
    success_url = 'invalid'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        any_event = self.request.organizer.events.first()
        kwargs['initial'] = {
            'currency': any_event.currency if any_event else settings.DEFAULT_CURRENCY,
            'secret': gen_giftcard_secret(self.request.organizer.settings.giftcard_length)
        }
        kwargs['organizer'] = self.request.organizer
        return kwargs

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, _('The gift card has been created and can now be used.'))
        form.instance.issuer = self.request.organizer
        super().form_valid(form)
        form.instance.transactions.create(
            value=form.cleaned_data['value']
        )
        form.instance.log_action('pretix.giftcards.created', user=self.request.user, data={})
        if form.cleaned_data['value']:
            form.instance.log_action('pretix.giftcards.transaction.manual', user=self.request.user, data={
                'value': form.cleaned_data['value']
            })
        return redirect(reverse(
            'control:organizer.giftcard',
            kwargs={
                'organizer': self.request.organizer.slug,
                'giftcard': self.object.pk
            }
        ))


class GiftCardUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    template_name = 'pretixcontrol/organizers/giftcard_edit.html'
    permission = 'can_manage_gift_cards'
    form_class = GiftCardUpdateForm
    success_url = 'invalid'
    context_object_name = 'card'
    model = GiftCard

    def get_object(self, queryset=None) -> Organizer:
        return get_object_or_404(
            self.request.organizer.issued_gift_cards,
            pk=self.kwargs.get('giftcard')
        )

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _('The gift card has been changed.'))
        super().form_valid(form)
        form.instance.log_action('pretix.giftcards.modified', user=self.request.user, data=dict(form.cleaned_data))
        return redirect(reverse(
            'control:organizer.giftcard',
            kwargs={
                'organizer': self.request.organizer.slug,
                'giftcard': self.object.pk
            }
        ))


class ExportMixin:
    @cached_property
    def exporters(self):
        exporters = []
        events = self.request.user.get_events_with_permission('can_view_orders', request=self.request).filter(
            organizer=self.request.organizer
        )
        responses = register_multievent_data_exporters.send(self.request.organizer)
        for ex in sorted([response(events) for r, response in responses if response], key=lambda ex: str(ex.verbose_name)):
            if self.request.GET.get("identifier") and ex.identifier != self.request.GET.get("identifier"):
                continue

            # Use form parse cycle to generate useful defaults
            test_form = ExporterForm(data=self.request.GET, prefix=ex.identifier)
            test_form.fields = ex.export_form_fields
            test_form.is_valid()
            initial = {
                k: v for k, v in test_form.cleaned_data.items() if ex.identifier + "-" + k in self.request.GET
            }

            ex.form = ExporterForm(
                data=(self.request.POST if self.request.method == 'POST' else None),
                prefix=ex.identifier,
                initial=initial
            )
            ex.form.fields = ex.export_form_fields
            ex.form.fields.update([
                ('events',
                 forms.ModelMultipleChoiceField(
                     queryset=events,
                     initial=events,
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     label=_('Events'),
                     required=True
                 )),
            ])
            exporters.append(ex)
        return exporters


class ExportDoView(OrganizerPermissionRequiredMixin, ExportMixin, AsyncAction, View):
    known_errortypes = ['ExportError']
    task = multiexport

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return reverse('cachedfile.download', kwargs={'id': str(value)})

    def get_error_url(self):
        return reverse('control:organizer.export', kwargs={
            'organizer': self.request.organizer.slug
        })

    @cached_property
    def exporter(self):
        for ex in self.exporters:
            if ex.identifier == self.request.POST.get("exporter"):
                return ex

    def post(self, request, *args, **kwargs):
        if not self.exporter:
            messages.error(self.request, _('The selected exporter was not found.'))
            return redirect('control:organizer.export', kwargs={
                'organizer': self.request.organizer.slug
            })

        if not self.exporter.form.is_valid():
            messages.error(self.request, _('There was a problem processing your input. See below for error details.'))
            return self.get(request, *args, **kwargs)

        cf = CachedFile(web_download=True, session_key=request.session.session_key)
        cf.date = now()
        cf.expires = now() + timedelta(hours=24)
        cf.save()
        return self.do(
            organizer=self.request.organizer.id,
            user=self.request.user.id,
            fileid=str(cf.id),
            provider=self.exporter.identifier,
            device=None,
            token=None,
            form_data=self.exporter.form.cleaned_data
        )


class ExportView(OrganizerPermissionRequiredMixin, ExportMixin, TemplateView):
    template_name = 'pretixcontrol/organizers/export.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exporters'] = self.exporters
        return ctx


class GateListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = Gate
    template_name = 'pretixcontrol/organizers/gates.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'gates'

    def get_queryset(self):
        return self.request.organizer.gates.all()


class GateCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = Gate
    template_name = 'pretixcontrol/organizers/gate_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = GateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Gate, organizer=self.request.organizer, pk=self.kwargs.get('gate'))

    def get_success_url(self):
        return reverse('control:organizer.gates', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        messages.success(self.request, _('The gate has been created.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.gate.created', user=self.request.user, data={
            k: getattr(self.object, k) for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class GateUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = Gate
    template_name = 'pretixcontrol/organizers/gate_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'gate'
    form_class = GateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Gate, organizer=self.request.organizer, pk=self.kwargs.get('gate'))

    def get_success_url(self):
        return reverse('control:organizer.gates', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.gate.changed', user=self.request.user, data={
                k: getattr(self.object, k)
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class GateDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DeleteView):
    model = Gate
    template_name = 'pretixcontrol/organizers/gate_delete.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'gate'

    def get_object(self, queryset=None):
        return get_object_or_404(Gate, organizer=self.request.organizer, pk=self.kwargs.get('gate'))

    def get_success_url(self):
        return reverse('control:organizer.gates', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        self.object.log_action('pretix.gate.deleted', user=self.request.user)
        self.object.delete()
        messages.success(request, _('The selected gate has been deleted.'))
        return redirect(success_url)
