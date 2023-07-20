#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Bolutife Lawrence, Jakob Schnell, Sohalt
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import re
from datetime import time, timedelta
from decimal import Decimal
from hashlib import sha1

import bleach
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import connections, transaction
from django.db.models import (
    Count, Exists, F, IntegerField, Max, Min, OuterRef, Prefetch,
    ProtectedError, Q, Subquery, Sum,
)
from django.db.models.functions import Coalesce, Greatest
from django.forms import DecimalField
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import get_current_timezone, now
from django.utils.translation import gettext, gettext_lazy as _
from django.views import View
from django.views.generic import (
    CreateView, DetailView, FormView, ListView, TemplateView, UpdateView,
)

from pretix.api.models import ApiCall, WebHook
from pretix.api.webhooks import manually_retry_all_calls
from pretix.base.auth import get_auth_backends
from pretix.base.channels import get_all_sales_channels
from pretix.base.exporter import OrganizerLevelExportMixin
from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, Customer, Device, Gate, GiftCard, Invoice, LogEntry,
    Membership, MembershipType, Order, OrderPayment, OrderPosition, Organizer,
    ReusableMedium, ScheduledOrganizerExport, Team, TeamInvite, User,
)
from pretix.base.models.customers import CustomerSSOClient, CustomerSSOProvider
from pretix.base.models.event import Event, EventMetaProperty, EventMetaValue
from pretix.base.models.giftcards import (
    GiftCardAcceptance, GiftCardTransaction, gen_giftcard_secret,
)
from pretix.base.models.orders import CancellationRequest
from pretix.base.models.organizer import TeamAPIToken
from pretix.base.payment import PaymentException
from pretix.base.services.export import multiexport, scheduled_organizer_export
from pretix.base.services.mail import SendMailException, mail
from pretix.base.settings import SETTINGS_AFFECTING_CSS
from pretix.base.signals import register_multievent_data_exporters
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.exports import ScheduledOrganizerExportForm
from pretix.control.forms.filter import (
    CustomerFilterForm, DeviceFilterForm, EventFilterForm, GiftCardFilterForm,
    OrganizerFilterForm, ReusableMediaFilterForm, TeamFilterForm,
)
from pretix.control.forms.orders import ExporterForm
from pretix.control.forms.organizer import (
    CustomerCreateForm, CustomerUpdateForm, DeviceBulkEditForm, DeviceForm,
    EventMetaPropertyForm, GateForm, GiftCardAcceptanceInviteForm,
    GiftCardCreateForm, GiftCardUpdateForm, MailSettingsForm,
    MembershipTypeForm, MembershipUpdateForm, OrganizerDeleteForm,
    OrganizerFooterLinkFormset, OrganizerForm, OrganizerSettingsForm,
    OrganizerUpdateForm, ReusableMediumCreateForm, ReusableMediumUpdateForm,
    SSOClientForm, SSOProviderForm, TeamForm, WebHookForm,
)
from pretix.control.forms.rrule import RRuleForm
from pretix.control.logdisplay import OVERVIEW_BANLIST
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, OrganizerPermissionRequiredMixin,
)
from pretix.control.signals import nav_organizer
from pretix.control.views import PaginationMixin
from pretix.control.views.mailsetup import MailSettingsSetupView
from pretix.helpers import OF_SELF, GroupConcat
from pretix.helpers.compat import CompatDeleteView
from pretix.helpers.dicts import merge_dicts
from pretix.helpers.format import format_map
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.forms.customer import TokenGenerator
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
        qs = self.request.user.get_events_with_any_permission(self.request).select_related(
            'organizer').prefetch_related(
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
            self.filter_form['meta_{}'.format(p.name)] for p in
            self.organizer.meta_properties.filter(filter_allowed=True)
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


class OrganizerMailSettings(OrganizerSettingsFormView):
    form_class = MailSettingsForm
    template_name = 'pretixcontrol/organizers/mail.html'
    permission = 'can_change_organizer_settings'

    def get_success_url(self):
        return reverse('control:organizer.settings.mail', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.organizer.log_action(
                    'pretix.organizer.settings', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )
                messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)


class MailSettingsSetup(OrganizerPermissionRequiredMixin, MailSettingsSetupView):
    permission = 'can_change_organizer_settings'
    basetpl = 'pretixcontrol/base.html'

    def get_success_url(self):
        return reverse('control:organizer.settings.mail', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def log_action(self, data):
        self.request.organizer.log_action(
            'pretix.organizer.settings', user=self.request.user, data=data
        )


class MailSettingsPreview(OrganizerPermissionRequiredMixin, View):
    permission = 'can_change_organizer_settings'

    # return the origin text if key is missing in dict
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'

    # create index-language mapping
    @cached_property
    def supported_locale(self):
        locales = {}
        for idx, val in enumerate(settings.LANGUAGES):
            if val[0] in self.request.organizer.settings.locales:
                locales[str(idx)] = val[0]
        return locales

    # get all supported placeholders with dummy values
    def placeholders(self, item):
        ctx = {}
        for p, s in MailSettingsForm(obj=self.request.organizer)._get_sample_context(
                MailSettingsForm.base_context[item]).items():
            if s.strip().startswith('*'):
                ctx[p] = s
            else:
                ctx[p] = '<span class="placeholder" title="{}">{}</span>'.format(
                    _('This value will be replaced based on dynamic parameters.'),
                    s
                )
        return self.SafeDict(ctx)

    def post(self, request, *args, **kwargs):
        preview_item = request.POST.get('item', '')
        if preview_item not in MailSettingsForm.base_context:
            return HttpResponseBadRequest(_('invalid item'))

        regex = r"^" + re.escape(preview_item) + r"_(?P<idx>[\d]+)$"
        msgs = {}
        for k, v in request.POST.items():
            # only accept allowed fields
            matched = re.search(regex, k)
            if matched is not None:
                idx = matched.group('idx')
                if idx in self.supported_locale:
                    with language(self.supported_locale[idx], self.request.organizer.settings.region):
                        if k.startswith('mail_subject_'):
                            msgs[self.supported_locale[idx]] = format_map(bleach.clean(v),
                                                                          self.placeholders(preview_item))
                        else:
                            msgs[self.supported_locale[idx]] = markdown_compile_email(
                                format_map(v, self.placeholders(preview_item))
                            )

        return JsonResponse({
            'item': preview_item,
            'msgs': msgs
        })


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
                self.request.organizer = None
            messages.success(self.request, _('The organizer has been deleted.'))
            return redirect(self.get_success_url())
        except ProtectedError as e:
            err = gettext(
                'The organizer could not be deleted as some constraints (e.g. data created by plug-ins) do not allow it.')

            # Unlike deleting events (which is done by regular backend users), this feature can only be used by sysadmins,
            # so we expose more technical / less polished information.
            affected_models = set()
            for m in e.protected_objects:
                affected_models.add(type(m)._meta.label)

            if affected_models:
                err += ' ' + gettext(
                    'The following database models still contain data that cannot be deleted automatically: {affected_models}'
                ).format(
                    affected_models=', '.join(list(affected_models))
                )

            messages.error(self.request, err)
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
            is_admin=self.request.user.has_active_staff_session(self.request.session.session_key),
            data=self.request.POST if self.request.method == 'POST' else None,
            files=self.request.FILES if self.request.method == 'POST' else None
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['sform'] = self.sform
        context['footer_links_formset'] = self.footer_links_formset
        return context

    @transaction.atomic
    def form_valid(self, form):
        self.sform.save()
        self.save_footer_links_formset(self.object)
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
            if any(p in self.sform.changed_data for p in SETTINGS_AFFECTING_CSS):
                change_css = True
        if self.footer_links_formset.has_changed():
            self.request.organizer.log_action('pretix.organizer.footerlinks.changed', user=self.request.user, data={
                'data': self.footer_links_formset.cleaned_data
            })
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
        if form.is_valid() and self.sform.is_valid() and self.footer_links_formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @cached_property
    def footer_links_formset(self):
        return OrganizerFooterLinkFormset(self.request.POST if self.request.method == "POST" else None,
                                          organizer=self.object,
                                          prefix="footer-links", instance=self.object)

    def save_footer_links_formset(self, obj):
        self.footer_links_formset.save()


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
            can_manage_customers=True, can_manage_reusable_media=True,
            can_view_orders=True, can_change_orders=True, can_view_vouchers=True, can_change_vouchers=True
        )
        t.members.add(self.request.user)
        return ret

    def get_success_url(self) -> str:
        return reverse('control:organizer', kwargs={
            'organizer': self.object.slug,
        })


class TeamListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, PaginationMixin, ListView):
    model = Team
    template_name = 'pretixcontrol/organizers/teams.html'
    permission = 'can_change_teams'
    context_object_name = 'teams'

    def get_queryset(self):
        qs = self.request.organizer.teams.annotate(
            memcount=Count('members', distinct=True),
            eventcount=Count('limit_events', distinct=True),
            invcount=Count('invites', distinct=True)
        ).all().order_by('name', 'pk')
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return TeamFilterForm(data=self.request.GET, request=self.request)


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


class TeamDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
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
        ).exists() or self.request.user.has_active_staff_session(self.request.session.session_key)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        if not self.is_allowed():
            messages.error(request, _('The selected team cannot be deleted.'))
            return redirect(success_url)

        try:
            self.object.log_action('pretix.team.deleted', user=self.request.user)
            self.object.delete()
        except ProtectedError:
            messages.error(
                self.request,
                _(
                    'The team could not be deleted as some constraints (e.g. data created by '
                    'plug-ins) do not allow it.'
                )
            )
            return redirect(success_url)

        messages.success(request, _('The selected team has been deleted.'))
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
                    'url': build_global_uri('control:auth.invite', kwargs={
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
                ).exists() or self.request.user.has_active_staff_session(self.request.session.session_key)
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


class DeviceQueryMixin:

    @cached_property
    def request_data(self):
        if self.request.method == "POST":
            d = self.request.POST
        else:
            d = self.request.GET
        d = d.copy()
        d.setdefault('state', 'active')
        return d

    @cached_property
    def filter_form(self):
        return DeviceFilterForm(
            data=self.request_data,
            request=self.request,
        )

    def get_queryset(self):
        qs = self.request.organizer.devices.prefetch_related(
            'limit_events', 'gate',
        ).order_by('revoked', '-device_id')
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        if 'device' in self.request_data and '__ALL' not in self.request_data:
            qs = qs.filter(
                id__in=self.request_data.getlist('device')
            )

        return qs


class DeviceListView(DeviceQueryMixin, OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = Device
    template_name = 'pretixcontrol/organizers/devices.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'devices'
    paginate_by = 100

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx


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

            # If the permission of the device have changed, let's clear "permission denied" errors from the idempotency store
            auth_hash_parts = f'Device {self.object.api_token}:'
            auth_hash = sha1(auth_hash_parts.encode()).hexdigest()
            ApiCall.objects.filter(
                auth_hash=auth_hash,
                response_code=403,
            ).delete()

        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class DeviceBulkUpdateView(DeviceQueryMixin, OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/organizers/device_bulk_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'device'
    form_class = DeviceBulkEditForm

    def get_queryset(self):
        return super().get_queryset().prefetch_related(None).order_by()

    def get(self, request, *args, **kwargs):
        return HttpResponse(status=405)

    @cached_property
    def is_submitted(self):
        # Usually, django considers a form "bound" / "submitted" on every POST request. However, this view is always
        # called with POST method, even if just to pass the selection of objects to work on, so we want to modify
        # that behaviour
        return '_bulk' in self.request.POST

    def get_form_kwargs(self):
        initial = {}
        mixed_values = set()
        qs = self.get_queryset().annotate(
            limit_events_list=Subquery(
                Device.limit_events.through.objects.filter(
                    device_id=OuterRef('pk')
                ).order_by('device_id', 'event_id').values('device_id').annotate(
                    g=GroupConcat('event_id', separator=',')
                ).values('g')
            )
        )

        fields = {
            'all_events': 'all_events',
            'limit_events': 'limit_events_list',
            'security_profile': 'security_profile',
            'gate': 'gate',
        }
        for k, f in fields.items():
            existing_values = list(qs.order_by(f).values(f).annotate(c=Count('*')))
            if len(existing_values) == 1:
                if k == 'limit_events':
                    if existing_values[0][f]:
                        initial[k] = self.request.organizer.events.filter(id__in=existing_values[0][f].split(","))
                    else:
                        initial[k] = []
                else:
                    initial[k] = existing_values[0][f]
            elif len(existing_values) > 1:
                mixed_values.add(k)
                initial[k] = None

        kwargs = super().get_form_kwargs()
        kwargs['organizer'] = self.request.organizer
        kwargs['prefix'] = 'bulkedit'
        kwargs['initial'] = initial
        kwargs['queryset'] = self.get_queryset()
        kwargs['mixed_values'] = mixed_values
        if not self.is_submitted:
            kwargs['data'] = None
            kwargs['files'] = None
        return kwargs

    def get_object(self, queryset=None):
        return get_object_or_404(Device, organizer=self.request.organizer, pk=self.kwargs.get('device'))

    def get_success_url(self):
        return reverse('control:organizer.devices', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic()
    def form_valid(self, form):
        log_entries = []

        # Main form
        form.save()
        data = {
            k: (v if k != 'limit_events' else [e.id for e in v])
            for k, v in form.cleaned_data.items()
            if k in form.changed_data
        }
        data['_raw_bulk_data'] = self.request.POST.dict()
        for obj in self.get_queryset():
            log_entries.append(
                obj.log_action('pretix.device.changed', data=data, user=self.request.user, save=False)
            )

        if connections['default'].features.can_return_rows_from_bulk_insert:
            LogEntry.objects.bulk_create(log_entries, batch_size=200)
            LogEntry.bulk_postprocess(log_entries)
        else:
            for le in log_entries:
                le.save()
            LogEntry.bulk_postprocess(log_entries)

        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['devices'] = self.get_queryset()
        ctx['bulk_selected'] = self.request.POST.getlist("_bulk")
        return ctx

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        is_valid = (
            self.is_submitted and
            form.is_valid()
        )
        if is_valid:
            return self.form_valid(form)
        else:
            if self.is_submitted:
                messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.form_invalid(form)


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
        if self.object.revoked:
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
        ctx['retry_count'] = self.webhook.retries.count()
        return ctx

    @cached_property
    def webhook(self):
        return get_object_or_404(
            WebHook, organizer=self.request.organizer, pk=self.kwargs.get('webhook')
        )

    def get_queryset(self):
        return self.webhook.calls.order_by('-datetime')

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "expedite":
            self.request.organizer.log_action('pretix.webhook.retries.expedited', user=self.request.user, data={
                'webhook': self.webhook.pk,
            })
            manually_retry_all_calls.apply_async(args=(self.webhook.pk,))
            messages.success(request, _('All requests will now be scheduled for an immediate attempt. Please '
                                        'allow for a few minutes before they are processed.'))
        elif request.POST.get("action") == "drop":
            self.request.organizer.log_action('pretix.webhook.retries.dropped', user=self.request.user, data={
                'webhook': self.webhook.pk,
            })
            self.webhook.retries.all().delete()
            messages.success(request, _('All unprocessed webhooks have been stopped from retrying.'))
        return redirect(reverse('control:organizer.webhook.logs', kwargs={
            'organizer': self.request.organizer.slug,
            'webhook': self.webhook.pk,
        }))


class GiftCardAcceptanceInviteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, FormView):
    model = GiftCardAcceptance
    template_name = 'pretixcontrol/organizers/giftcard_acceptance_invite.html'
    permission = 'can_change_organizer_settings'
    form_class = GiftCardAcceptanceInviteForm

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'organizer': self.request.organizer,
        }

    def form_valid(self, form):
        self.request.organizer.gift_card_acceptor_acceptance.get_or_create(
            acceptor=form.cleaned_data['acceptor'],
            reusable_media=form.cleaned_data['reusable_media'],
            active=False,
        )
        self.request.organizer.log_action(
            'pretix.giftcards.acceptance.acceptor.invited',
            data={'acceptor': form.cleaned_data['acceptor'].slug,
                  'reusable_media': form.cleaned_data['reusable_media']},
            user=self.request.user
        )
        messages.success(self.request, _('The selected organizer has been invited.'))
        return redirect(
            reverse('control:organizer.giftcards.acceptance', kwargs={'organizer': self.request.organizer.slug}))


class GiftCardAcceptanceListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = GiftCardAcceptance
    template_name = 'pretixcontrol/organizers/giftcard_acceptance_list.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'acceptor_acceptance'
    paginate_by = 50

    def get_queryset(self):
        qs = self.request.organizer.gift_card_acceptor_acceptance.select_related(
            'acceptor'
        ).order_by('acceptor__name', 'acceptor_id')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['issuer_acceptance'] = self.request.organizer.gift_card_issuer_acceptance.select_related(
            'issuer'
        )
        return ctx

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        if "delete_acceptor" in request.POST:
            done = self.request.organizer.gift_card_acceptor_acceptance.filter(
                acceptor__slug=request.POST.get("delete_acceptor")
            ).delete()
            if done:
                self.request.organizer.log_action(
                    'pretix.giftcards.acceptance.acceptor.removed',
                    data={'acceptor': request.POST.get("delete_acceptor")},
                    user=request.user
                )
            messages.success(self.request, _('The selected connection has been removed.'))
        elif "delete_issuer" in request.POST:
            done = self.request.organizer.gift_card_issuer_acceptance.filter(
                issuer__slug=request.POST.get("delete_issuer")
            ).delete()
            if done:
                self.request.organizer.log_action(
                    'pretix.giftcards.acceptance.issuer.removed',
                    data={'issuer': request.POST.get("delete_acceptor")},
                    user=request.user
                )
            messages.success(self.request, _('The selected connection has been removed.'))
        if "accept_issuer" in request.POST:
            done = self.request.organizer.gift_card_issuer_acceptance.filter(
                issuer__slug=request.POST.get("accept_issuer")
            ).update(active=True)
            if done:
                self.request.organizer.log_action(
                    'pretix.giftcards.acceptance.issuer.accepted',
                    data={'issuer': request.POST.get("accept_issuer")},
                    user=request.user
                )
            messages.success(self.request, _('The selected connection has been accepted.'))

        return redirect(
            reverse('control:organizer.giftcards.acceptance', kwargs={'organizer': self.request.organizer.slug}))


class GiftCardListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = GiftCard
    template_name = 'pretixcontrol/organizers/giftcards.html'
    permission = 'can_manage_gift_cards'
    context_object_name = 'giftcards'
    paginate_by = 50

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
        self.object = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=self.get_object().pk)
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
                t.order.log_action('pretix.event.order.payment.started', {
                    'local_id': r.local_id,
                    'provider': r.provider
                }, user=request.user)
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
        elif request.POST.get('value'):
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
                        acceptor=request.organizer,
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

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            transactions=self.object.transactions.select_related(
                'order', 'order__event', 'order__event__organizer', 'payment', 'refund'
            ).prefetch_related(
                'acceptor'
            )
        )


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
            acceptor=self.request.organizer,
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
    def exporter(self):
        id = self.request.GET.get("identifier") or self.request.POST.get("exporter") or self.request.GET.get("exporter")
        if not id:
            return None
        for ex in self.exporters:
            if id != ex.identifier:
                continue
            if self.scheduled:
                initial = dict(self.scheduled.export_form_data)

                test_form = ExporterForm(data=self.request.GET, prefix=ex.identifier)
                test_form.fields = ex.export_form_fields
                for k in initial:
                    if initial[k] and k in test_form.fields:
                        try:
                            initial[k] = test_form.fields[k].to_python(initial[k])
                        except Exception:
                            pass
            else:
                # Use form parse cycle to generate useful defaults
                test_form = ExporterForm(data=self.request.GET, prefix=ex.identifier)
                test_form.fields = ex.export_form_fields
                test_form.is_valid()
                initial = {
                    k: v for k, v in test_form.cleaned_data.items() if ex.identifier + "-" + k in self.request.GET
                }
                if 'events' not in initial:
                    initial.setdefault('all_events', True)

            ex.form = ExporterForm(
                data=(self.request.POST if self.request.method == 'POST' else None),
                prefix=ex.identifier,
                initial=initial
            )
            ex.form.fields = ex.export_form_fields
            if not isinstance(ex, OrganizerLevelExportMixin):
                ex.form.fields.update([
                    ('all_events',
                     forms.BooleanField(
                         label=_("All events (that I have access to)"),
                         required=False
                     )),
                    ('events',
                     forms.ModelMultipleChoiceField(
                         queryset=self.events,
                         widget=forms.CheckboxSelectMultiple(
                             attrs={
                                 'class': 'scrolling-multiple-choice',
                                 'data-inverse-dependency': f'#id_{ex.identifier}-all_events',
                             }
                         ),
                         label=_('Events'),
                         required=False
                     )),
                ])
            return ex

    @cached_property
    def events(self):
        return self.request.user.get_events_with_permission('can_view_orders', request=self.request).filter(
            organizer=self.request.organizer
        )

    @cached_property
    def exporters(self):
        responses = register_multievent_data_exporters.send(self.request.organizer)
        raw_exporters = [
            response(Event.objects.none() if issubclass(response, OrganizerLevelExportMixin) else self.events,
                     self.request.organizer)
            for r, response in responses
            if response
        ]
        raw_exporters = [
            ex for ex in raw_exporters
            if (
                not isinstance(ex, OrganizerLevelExportMixin) or
                self.request.user.has_organizer_permission(self.request.organizer, ex.organizer_required_permission,
                                                           self.request)
            ) and ex.available_for_user(self.request.user if self.request.user and self.request.user.is_authenticated else None)
        ]
        return sorted(
            raw_exporters,
            key=lambda ex: (
                0 if ex.category else 1, ex.category or "", 0 if ex.featured else 1, str(ex.verbose_name).lower())
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exporter'] = self.exporter
        ctx['exporters'] = self.exporters
        return ctx

    def get_scheduled_queryset(self):
        if not self.request.user.has_organizer_permission(self.request.organizer, 'can_change_organizer_settings',
                                                          request=self.request):
            qs = self.request.organizer.scheduled_exports.filter(owner=self.request.user)
        else:
            qs = self.request.organizer.scheduled_exports
        return qs.select_related('owner').order_by('export_identifier', 'schedule_next_run')

    @cached_property
    def scheduled(self):
        if "scheduled" in self.request.POST:
            return get_object_or_404(self.get_scheduled_queryset(), pk=self.request.POST.get("scheduled"))
        elif "scheduled" in self.request.GET:
            return get_object_or_404(self.get_scheduled_queryset(), pk=self.request.GET.get("scheduled"))


class ExportDoView(OrganizerPermissionRequiredMixin, ExportMixin, AsyncAction, TemplateView):
    known_errortypes = ['ExportError']
    task = multiexport
    template_name = 'pretixcontrol/organizers/export_form.html'

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return reverse('cachedfile.download', kwargs={'id': str(value)})

    def get_error_url(self):
        return reverse('control:organizer.export', kwargs={
            'organizer': self.request.organizer.slug
        })

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return TemplateView.get(self, request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not self.exporter:
            messages.error(self.request, _('The selected exporter was not found.'))
            return redirect('control:organizer.export', kwargs={
                'organizer': self.request.organizer.slug
            })

        if self.scheduled:
            data = self.scheduled.export_form_data
        else:
            if not self.exporter.form.is_valid():
                messages.error(self.request,
                               _('There was a problem processing your input. See below for error details.'))
                return self.get(request, *args, **kwargs)
            data = self.exporter.form.cleaned_data

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
            form_data=data,
            staff_session=self.request.user.has_active_staff_session(self.request.session.session_key)
        )


class ExportView(OrganizerPermissionRequiredMixin, ExportMixin, ListView):
    paginate_by = 25
    context_object_name = 'scheduled'

    def get_template_names(self):
        if self.exporter:
            return ['pretixcontrol/organizers/export_form.html']
        return ['pretixcontrol/organizers/export.html']

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        if request.POST.get("schedule") == "save":
            if self.exporter.form.is_valid() and self.rrule_form.is_valid() and self.schedule_form.is_valid():
                self.schedule_form.instance.export_identifier = self.exporter.identifier
                self.schedule_form.instance.export_form_data = self.exporter.form.cleaned_data
                self.schedule_form.instance.schedule_rrule = str(self.rrule_form.to_rrule())
                self.schedule_form.instance.error_counter = 0
                self.schedule_form.instance.error_last_message = None
                self.schedule_form.instance.compute_next_run()
                self.schedule_form.instance.save()
                if self.schedule_form.instance.schedule_next_run:
                    messages.success(
                        request,
                        _('Your export schedule has been saved. The next export will start around {datetime}.').format(
                            datetime=date_format(self.schedule_form.instance.schedule_next_run, 'SHORT_DATETIME_FORMAT')
                        )
                    )
                else:
                    messages.warning(request, _('Your export schedule has been saved, but no next export is planned.'))
                self.request.organizer.log_action(
                    'pretix.organizer.export.schedule.changed' if self.scheduled else 'pretix.organizer.export.schedule.added',
                    user=self.request.user, data={
                        'id': self.schedule_form.instance.id,
                        'export_identifier': self.exporter.identifier,
                        'export_form_data': self.exporter.form.cleaned_data,
                        'schedule_rrule': self.schedule_form.instance.schedule_rrule,
                        **self.schedule_form.cleaned_data,
                    }
                )
                return redirect(reverse('control:organizer.export', kwargs={
                    'organizer': self.request.organizer.slug
                }))
            else:
                return super().get(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)

    @cached_property
    def rrule_form(self):
        if self.scheduled:
            initial = RRuleForm.initial_from_rrule(self.scheduled.schedule_rrule)
        else:
            initial = {}
        return RRuleForm(
            data=self.request.POST if self.request.method == 'POST' and self.request.POST.get(
                "schedule") == "save" else None,
            prefix="rrule",
            initial=initial
        )

    @cached_property
    def schedule_form(self):
        instance = self.scheduled or ScheduledOrganizerExport(
            organizer=self.request.organizer,
            owner=self.request.user,
            timezone=str(get_current_timezone()),
        )
        if not self.scheduled:
            initial = {
                "mail_subject": gettext("Export: {title}").format(title=self.exporter.verbose_name),
                "mail_template": gettext(
                    "Hello,\n\nattached to this email, you can find a new scheduled report for {name}.").format(
                    name=str(self.request.organizer.name)
                ),
                "schedule_rrule_time": time(4, 0, 0),
            }
        else:
            initial = {}
        return ScheduledOrganizerExportForm(
            data=self.request.POST if self.request.method == 'POST' and self.request.POST.get(
                "schedule") == "save" else None,
            prefix="schedule",
            instance=instance,
            initial=initial,
        )

    def get_queryset(self):
        return self.get_scheduled_queryset()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if "schedule" in self.request.POST or self.scheduled:
            ctx['schedule_form'] = self.schedule_form
            ctx['rrule_form'] = self.rrule_form
        elif not self.exporter:
            for s in ctx['scheduled']:
                try:
                    s.export_verbose_name = [e for e in self.exporters if e.identifier == s.export_identifier][
                        0].verbose_name
                except IndexError:
                    s.export_verbose_name = "?"
        return ctx


class DeleteScheduledExportView(OrganizerPermissionRequiredMixin, ExportMixin, CompatDeleteView):
    template_name = 'pretixcontrol/organizers/export_delete.html'
    context_object_name = 'export'

    def get_queryset(self):
        return self.get_scheduled_queryset()

    def get_success_url(self):
        return reverse('control:organizer.export', kwargs={
            'organizer': self.request.organizer.slug
        })

    @transaction.atomic()
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        self.request.organizer.log_action('pretix.organizer.export.schedule.deleted', user=self.request.user, data={
            'id': self.object.id,
        })
        return redirect(self.get_success_url())


class RunScheduledExportView(OrganizerPermissionRequiredMixin, ExportMixin, View):

    def post(self, request, *args, **kwargs):
        s = get_object_or_404(self.get_scheduled_queryset(), pk=kwargs.get('pk'))
        scheduled_organizer_export.apply_async(
            kwargs={
                'organizer': s.organizer_id,
                'schedule': s.pk,
            },
            # Scheduled exports usually run on the low-prio queue "background" but if they're manually triggered,
            # we run them with normal priority
            queue='default',
        )
        messages.success(self.request, _('Your export is queued to start soon. The results will be send via email. '
                                         'Depending on system load and type and size of export, this may take a few '
                                         'minutes.'))
        return redirect(reverse('control:organizer.export', kwargs={
            'organizer': self.request.organizer.slug
        }))


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


class GateDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
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


class EventMetaPropertyListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = EventMetaProperty
    template_name = 'pretixcontrol/organizers/properties.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'properties'

    def get_queryset(self):
        return self.request.organizer.meta_properties.all()


class EventMetaPropertyCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = EventMetaProperty
    template_name = 'pretixcontrol/organizers/property_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = EventMetaPropertyForm

    def get_object(self, queryset=None):
        return get_object_or_404(EventMetaProperty, organizer=self.request.organizer, pk=self.kwargs.get('property'))

    def get_success_url(self):
        return reverse('control:organizer.properties', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        messages.success(self.request, _('The property has been created.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.property.created', user=self.request.user, data={
            k: getattr(self.object, k) for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class EventMetaPropertyUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = EventMetaProperty
    template_name = 'pretixcontrol/organizers/property_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'property'
    form_class = EventMetaPropertyForm

    def get_object(self, queryset=None):
        return get_object_or_404(EventMetaProperty, organizer=self.request.organizer, pk=self.kwargs.get('property'))

    def get_success_url(self):
        return reverse('control:organizer.properties', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.property.changed', user=self.request.user, data={
                k: getattr(self.object, k)
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class EventMetaPropertyDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
    model = EventMetaProperty
    template_name = 'pretixcontrol/organizers/property_delete.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'property'

    def get_object(self, queryset=None):
        return get_object_or_404(EventMetaProperty, organizer=self.request.organizer, pk=self.kwargs.get('property'))

    def get_success_url(self):
        return reverse('control:organizer.properties', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        self.object.log_action('pretix.property.deleted', user=self.request.user)
        self.object.delete()
        messages.success(request, _('The selected property has been deleted.'))
        return redirect(success_url)


class LogView(OrganizerPermissionRequiredMixin, PaginationMixin, ListView):
    template_name = 'pretixcontrol/organizers/logs.html'
    permission = 'can_change_organizer_settings'
    model = LogEntry
    context_object_name = 'logs'

    def get_queryset(self):
        # technically, we'd also need to sort by pk since this is a paginated list, but in this case we just can't
        # bear the performance cost
        qs = self.request.organizer.all_logentries().select_related(
            'user', 'content_type', 'api_token', 'oauth_application', 'device'
        ).order_by('-datetime')
        qs = qs.exclude(action_type__in=OVERVIEW_BANLIST)
        if self.request.GET.get('action_type'):
            qs = qs.filter(action_type=self.request.GET['action_type'])
        if self.request.GET.get('user'):
            qs = qs.filter(user_id=self.request.GET.get('user'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        return ctx


class MembershipTypeListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = MembershipType
    template_name = 'pretixcontrol/organizers/membershiptypes.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'types'

    def get_queryset(self):
        return self.request.organizer.membership_types.all()


class MembershipTypeCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = MembershipType
    template_name = 'pretixcontrol/organizers/membershiptype_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = MembershipTypeForm

    def get_object(self, queryset=None):
        return get_object_or_404(MembershipType, organizer=self.request.organizer, pk=self.kwargs.get('type'))

    def get_success_url(self):
        return reverse('control:organizer.membershiptypes', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _('The membership type has been created.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.membershiptype.created', user=self.request.user, data={
            k: getattr(self.object, k) for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class MembershipTypeUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = MembershipType
    template_name = 'pretixcontrol/organizers/membershiptype_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'type'
    form_class = MembershipTypeForm

    def get_object(self, queryset=None):
        return get_object_or_404(MembershipType, organizer=self.request.organizer, pk=self.kwargs.get('type'))

    def get_success_url(self):
        return reverse('control:organizer.membershiptypes', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.membershiptype.changed', user=self.request.user, data={
                k: getattr(self.object, k)
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class MembershipTypeDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
    model = MembershipType
    template_name = 'pretixcontrol/organizers/membershiptype_delete.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'type'

    def get_object(self, queryset=None):
        return get_object_or_404(MembershipType, organizer=self.request.organizer, pk=self.kwargs.get('type'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_allowed'] = self.object.allow_delete()
        return ctx

    def get_success_url(self):
        return reverse('control:organizer.membershiptypes', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        if self.object.allow_delete():
            self.object.log_action('pretix.membershiptype.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected object has been deleted.'))
        return redirect(success_url)


class SSOProviderListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = CustomerSSOProvider
    template_name = 'pretixcontrol/organizers/ssoproviders.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'providers'

    def get_queryset(self):
        return self.request.organizer.sso_providers.all()


class SSOProviderCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = CustomerSSOProvider
    template_name = 'pretixcontrol/organizers/ssoprovider_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = SSOProviderForm

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOProvider, organizer=self.request.organizer, pk=self.kwargs.get('provider'))

    def get_success_url(self):
        return reverse('control:organizer.ssoproviders', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, _('The provider has been created.'))
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.ssoprovider.created', user=self.request.user, data={
            k: getattr(self.object, k, self.object.configuration.get(k)) for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class SSOProviderUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = CustomerSSOProvider
    template_name = 'pretixcontrol/organizers/ssoprovider_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'provider'
    form_class = SSOProviderForm

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOProvider, organizer=self.request.organizer, pk=self.kwargs.get('provider'))

    def get_success_url(self):
        return reverse('control:organizer.ssoproviders', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['redirect_uri'] = build_absolute_uri(self.request.organizer, 'presale:organizer.customer.login.return',
                                                 kwargs={
                                                     'provider': self.object.pk
                                                 })
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.ssoprovider.changed', user=self.request.user, data={
                k: getattr(self.object, k, self.object.configuration.get(k)) for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class SSOProviderDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
    model = CustomerSSOProvider
    template_name = 'pretixcontrol/organizers/ssoprovider_delete.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'provider'

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOProvider, organizer=self.request.organizer, pk=self.kwargs.get('provider'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_allowed'] = self.object.allow_delete()
        return ctx

    def get_success_url(self):
        return reverse('control:organizer.ssoproviders', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        if self.object.allow_delete():
            self.object.log_action('pretix.ssoprovider.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected object has been deleted.'))
        return redirect(success_url)


class SSOClientListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, ListView):
    model = CustomerSSOClient
    template_name = 'pretixcontrol/organizers/ssoclients.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'clients'

    def get_queryset(self):
        return self.request.organizer.sso_clients.all()


class SSOClientCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    model = CustomerSSOClient
    template_name = 'pretixcontrol/organizers/ssoclient_edit.html'
    permission = 'can_change_organizer_settings'
    form_class = SSOClientForm

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOClient, organizer=self.request.organizer, pk=self.kwargs.get('client'))

    def get_success_url(self):
        return reverse('control:organizer.ssoclient.edit', kwargs={
            'organizer': self.request.organizer.slug,
            'client': self.object.pk
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        secret = form.instance.set_client_secret()
        messages.success(
            self.request,
            _('The SSO client has been created. Please note down the following client secret, it will never be shown '
              'again: {secret}').format(secret=secret)
        )
        form.instance.organizer = self.request.organizer
        ret = super().form_valid(form)
        form.instance.log_action('pretix.ssoclient.created', user=self.request.user, data={
            k: getattr(self.object, k, form.cleaned_data.get(k)) for k in form.changed_data
        })
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class SSOClientUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    model = CustomerSSOClient
    template_name = 'pretixcontrol/organizers/ssoclient_edit.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'client'
    form_class = SSOClientForm

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOClient, organizer=self.request.organizer, pk=self.kwargs.get('client'))

    def get_success_url(self):
        return reverse('control:organizer.ssoclient.edit', kwargs={
            'organizer': self.request.organizer.slug,
            'client': self.object.pk
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.organizer
        return kwargs

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.ssoclient.changed', user=self.request.user, data={
                k: getattr(self.object, k, form.cleaned_data.get(k)) for k in form.changed_data
            })
        if form.cleaned_data.get('regenerate_client_secret'):
            secret = form.instance.set_client_secret()
            messages.success(
                self.request,
                _('Your changes have been saved. Please note down the following client secret, it will never be shown '
                  'again: {secret}').format(secret=secret)
            )
        else:
            messages.success(
                self.request,
                _('Your changes have been saved.')
            )
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('Your changes could not be saved.'))
        return super().form_invalid(form)


class SSOClientDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
    model = CustomerSSOClient
    template_name = 'pretixcontrol/organizers/ssoclient_delete.html'
    permission = 'can_change_organizer_settings'
    context_object_name = 'client'

    def get_object(self, queryset=None):
        return get_object_or_404(CustomerSSOClient, organizer=self.request.organizer, pk=self.kwargs.get('client'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_allowed'] = self.object.allow_delete()
        return ctx

    def get_success_url(self):
        return reverse('control:organizer.ssoclients', kwargs={
            'organizer': self.request.organizer.slug,
        })

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        success_url = self.get_success_url()
        self.object = self.get_object()
        if self.object.allow_delete():
            self.object.log_action('pretix.ssoclient.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected object has been deleted.'))
        return redirect(success_url)


class CustomerListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, PaginationMixin, ListView):
    model = Customer
    template_name = 'pretixcontrol/organizers/customers.html'
    permission = 'can_manage_customers'
    context_object_name = 'customers'

    def get_queryset(self):
        qs = self.request.organizer.customers.all()
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return CustomerFilterForm(data=self.request.GET, request=self.request)


class CustomerDetailView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, PaginationMixin, ListView):
    template_name = 'pretixcontrol/organizers/customer.html'
    permission = 'can_manage_customers'
    context_object_name = 'orders'

    def get_queryset(self):
        q = Q(customer=self.customer)
        if self.request.organizer.settings.customer_accounts_link_by_email and self.customer.email:
            # This is safe because we only let customers with verified emails log in
            q |= Q(email__iexact=self.customer.email)
        qs = Order.objects.filter(
            q
        ).select_related('event').order_by('-datetime', 'pk')
        return qs

    @cached_property
    def customer(self):
        return get_object_or_404(
            self.request.organizer.customers,
            identifier=self.kwargs.get('customer')
        )

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'pwreset' and self.customer.provider_id is None:
            self.customer.log_action('pretix.customer.password.resetrequested', {}, user=self.request.user)
            ctx = self.customer.get_email_context()
            token = TokenGenerator().make_token(self.customer)
            ctx['url'] = build_absolute_uri(
                self.request.organizer,
                'presale:organizer.customer.recoverpw'
            ) + '?id=' + self.customer.identifier + '&token=' + token
            mail(
                self.customer.email,
                self.request.organizer.settings.mail_subject_customer_reset,
                self.request.organizer.settings.mail_text_customer_reset,
                ctx,
                locale=self.customer.locale,
                customer=self.customer,
                organizer=self.request.organizer,
            )
            messages.success(
                self.request,
                _('We\'ve sent the customer an email with further instructions on resetting your password.')
            )

        return redirect(reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.customer.identifier,
        }))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['customer'] = self.customer
        ctx['display_locale'] = dict(settings.LANGUAGES)[self.customer.locale or self.request.organizer.settings.locale]

        ctx['memberships'] = self.customer.memberships.with_usages().select_related(
            'membership_type', 'granted_in', 'granted_in__order', 'granted_in__order__event'
        )

        for m in ctx['memberships']:
            if m.membership_type.max_usages:
                m.percent = int(m.usages / m.membership_type.max_usages * 100)
            else:
                m.percent = 0

        # Only compute this annotations for this page (query optimization)
        s = OrderPosition.objects.filter(
            order=OuterRef('pk')
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        i = Invoice.objects.filter(
            order=OuterRef('pk'),
            is_cancellation=False,
            refered__isnull=True,
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        annotated = {
            o['pk']: o
            for o in
            Order.annotate_overpayments(Order.objects, sums=True).filter(
                pk__in=[o.pk for o in ctx['orders']]
            ).annotate(
                pcnt=Subquery(s, output_field=IntegerField()),
                icnt=Subquery(i, output_field=IntegerField()),
                has_cancellation_request=Exists(CancellationRequest.objects.filter(order=OuterRef('pk')))
            ).values(
                'pk', 'pcnt', 'is_overpaid', 'is_underpaid', 'is_pending_with_full_payment', 'has_external_refund',
                'has_pending_refund', 'has_cancellation_request', 'computed_payment_refund_sum', 'icnt'
            )
        }

        scs = get_all_sales_channels()
        for o in ctx['orders']:
            if o.pk not in annotated:
                continue
            o.pcnt = annotated.get(o.pk)['pcnt']
            o.is_overpaid = annotated.get(o.pk)['is_overpaid']
            o.is_underpaid = annotated.get(o.pk)['is_underpaid']
            o.is_pending_with_full_payment = annotated.get(o.pk)['is_pending_with_full_payment']
            o.has_external_refund = annotated.get(o.pk)['has_external_refund']
            o.has_pending_refund = annotated.get(o.pk)['has_pending_refund']
            o.has_cancellation_request = annotated.get(o.pk)['has_cancellation_request']
            o.computed_payment_refund_sum = annotated.get(o.pk)['computed_payment_refund_sum']
            o.icnt = annotated.get(o.pk)['icnt']
            o.sales_channel_obj = scs[o.sales_channel]

        ctx["lifetime_spending"] = (
            self.get_queryset()
            .filter(status=Order.STATUS_PAID)
            .values(currency=F("event__currency"))
            .order_by("currency")
            .annotate(spending=Sum("total"))
        )

        return ctx


class CustomerCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    template_name = 'pretixcontrol/organizers/customer_edit.html'
    permission = 'can_manage_customers'
    context_object_name = 'customer'
    form_class = CustomerCreateForm

    def get_form_kwargs(self):
        ctx = super().get_form_kwargs()
        c = Customer(organizer=self.request.organizer)
        c.assign_identifier()
        ctx['instance'] = c
        return ctx

    def form_valid(self, form):
        r = super().form_valid(form)
        form.instance.log_action('pretix.customer.created', user=self.request.user, data={
            k: getattr(form.instance, k)
            for k in form.changed_data
        })
        messages.success(self.request, _('Your changes have been saved.'))
        return r

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.object.identifier,
        })


class CustomerUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    template_name = 'pretixcontrol/organizers/customer_edit.html'
    permission = 'can_manage_customers'
    context_object_name = 'customer'
    form_class = CustomerUpdateForm

    def get_object(self, queryset=None):
        return get_object_or_404(
            self.request.organizer.customers,
            identifier=self.kwargs.get('customer')
        )

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.customer.changed', user=self.request.user, data={
                k: getattr(self.object, k)
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.object.identifier,
        })


class MembershipUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    template_name = 'pretixcontrol/organizers/customer_membership.html'
    permission = 'can_manage_customers'
    context_object_name = 'membership'
    form_class = MembershipUpdateForm

    def get_object(self, queryset=None):
        return get_object_or_404(
            Membership,
            customer__organizer=self.request.organizer,
            customer__identifier=self.kwargs.get('customer'),
            pk=self.kwargs.get('id')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['usages'] = self.object.orderposition_set.select_related(
            'order', 'order__event', 'subevent', 'item', 'variation',
        )
        return ctx

    def form_valid(self, form):
        if form.has_changed():
            d = {
                k: getattr(self.object, k)
                for k in form.changed_data
            }
            d['id'] = self.object.pk
            self.object.customer.log_action('pretix.customer.membership.changed', user=self.request.user, data=d)
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.object.customer.identifier,
        })


class MembershipDeleteView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CompatDeleteView):
    template_name = 'pretixcontrol/organizers/customer_membership_delete.html'
    permission = 'can_manage_customers'
    context_object_name = 'membership'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Membership,
            customer__organizer=self.request.organizer,
            customer__identifier=self.kwargs.get('customer'),
            testmode=True,
            pk=self.kwargs.get('id')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_allowed'] = self.object.allow_delete()
        return ctx

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.customer = self.object.customer
        success_url = self.get_success_url()
        if self.object.allow_delete():
            self.object.cartposition_set.all().delete()
            self.object.customer.log_action('pretix.customer.membership.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected object has been deleted.'))
        return redirect(success_url)

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.customer.identifier,
        })


class MembershipCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    template_name = 'pretixcontrol/organizers/customer_membership.html'
    permission = 'can_manage_customers'
    context_object_name = 'membership'
    form_class = MembershipUpdateForm

    @cached_property
    def customer(self):
        return get_object_or_404(
            self.request.organizer.customers,
            identifier=self.kwargs.get('customer')
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Membership(
            customer=self.customer,
        )
        return kwargs

    def form_valid(self, form):
        r = super().form_valid(form)
        d = {
            k: getattr(self.object, k)
            for k in form.changed_data
        }
        d['id'] = self.object.pk
        self.customer.log_action('pretix.customer.membership.created', user=self.request.user, data=d)
        messages.success(self.request, _('Your changes have been saved.'))
        return r

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.object.customer.identifier,
        })


class CustomerAnonymizeView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, DetailView):
    template_name = 'pretixcontrol/organizers/customer_anonymize.html'
    permission = 'can_manage_customers'
    context_object_name = 'customer'

    def get_object(self, queryset=None):
        return get_object_or_404(
            self.request.organizer.customers,
            identifier=self.kwargs.get('customer')
        )

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        with transaction.atomic():
            self.object.anonymize()
            self.object.log_action('pretix.customer.anonymized', user=self.request.user)
        messages.success(self.request, _('The customer account has been anonymized.'))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('control:organizer.customer', kwargs={
            'organizer': self.request.organizer.slug,
            'customer': self.object.identifier,
        })


class ReusableMediaListView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, PaginationMixin, ListView):
    model = ReusableMedium
    template_name = 'pretixcontrol/organizers/reusable_media.html'
    permission = 'can_manage_reusable_media'
    context_object_name = 'media'

    def get_queryset(self):
        qs = self.request.organizer.reusable_media.select_related(
            'customer', 'linked_orderposition', 'linked_orderposition__order', 'linked_orderposition__order__event',
            'linked_giftcard'
        )
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return ReusableMediaFilterForm(data=self.request.GET, request=self.request)


class ReusableMediumDetailView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/organizers/reusable_medium.html'
    permission = 'can_manage_reusable_media'

    @cached_property
    def medium(self):
        return get_object_or_404(
            self.request.organizer.reusable_media,
            pk=self.kwargs.get('pk')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['medium'] = self.medium
        return ctx


class ReusableMediumCreateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, CreateView):
    template_name = 'pretixcontrol/organizers/reusable_medium_edit.html'
    permission = 'can_manage_reusable_media'
    context_object_name = 'medium'
    form_class = ReusableMediumCreateForm

    def get_form_kwargs(self):
        ctx = super().get_form_kwargs()
        c = ReusableMedium(organizer=self.request.organizer)
        ctx['instance'] = c
        return ctx

    def form_valid(self, form):
        r = super().form_valid(form)
        form.instance.log_action('pretix.reusable_medium.created', user=self.request.user, data={
            k: getattr(form.instance, k)
            for k in form.changed_data
        })
        messages.success(self.request, _('Your changes have been saved.'))
        return r

    def get_success_url(self):
        return reverse('control:organizer.reusable_medium', kwargs={
            'organizer': self.request.organizer.slug,
            'pk': self.object.pk,
        })


class ReusableMediumUpdateView(OrganizerDetailViewMixin, OrganizerPermissionRequiredMixin, UpdateView):
    template_name = 'pretixcontrol/organizers/reusable_medium_edit.html'
    permission = 'can_manage_reusable_media'
    context_object_name = 'medium'
    form_class = ReusableMediumUpdateForm

    def get_object(self, queryset=None):
        return get_object_or_404(
            self.request.organizer.reusable_media,
            pk=self.kwargs.get('pk')
        )

    def form_valid(self, form):
        if form.has_changed():
            self.object.log_action('pretix.reusable_medium.changed', user=self.request.user, data={
                k: getattr(self.object, k)
                for k in form.changed_data
            })
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('control:organizer.reusable_medium', kwargs={
            'organizer': self.request.organizer.slug,
            'pk': self.object.pk,
        })
