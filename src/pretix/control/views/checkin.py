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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, jasonwaiting@live.hk, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
import secrets
from datetime import timezone

import dateutil.parser
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Prefetch, Q, Subquery
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import is_aware, make_aware, now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView, TemplateView
from i18nfield.strings import LazyI18nString

from pretix.api.views.checkin import _redeem_process
from pretix.base.media import MEDIA_TYPES
from pretix.base.models import Checkin, LogEntry, Order, OrderPosition
from pretix.base.models.checkin import CheckinList
from pretix.base.models.orders import PrintLog
from pretix.base.services.checkin import (
    LazyRuleVars, _logic_annotate_for_graphic_explain,
)
from pretix.base.signals import checkin_created
from pretix.base.views.tasks import AsyncFormView, AsyncPostView
from pretix.control.forms.checkin import (
    CheckinListForm, CheckinListSimulatorForm, CheckinResetForm,
)
from pretix.control.forms.filter import (
    CheckinFilterForm, CheckinListAttendeeFilterForm, CheckinListFilterForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, PaginationMixin, UpdateView
from pretix.helpers.compat import CompatDeleteView
from pretix.helpers.models import modelcopy


class CheckInListQueryMixin:

    @cached_property
    def request_data(self):
        if self.request.method == "POST":
            return self.request.POST
        return self.request.GET

    def get_queryset(self, filter=True):
        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.list.pk,
            type=Checkin.TYPE_ENTRY
        ).order_by('-datetime').values('position_id')
        cqs_exit = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.list.pk,
            type=Checkin.TYPE_EXIT
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        if self.list.include_pending:
            status_q = Q(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
        else:
            status_q = Q(
                Q(order__status=Order.STATUS_PAID) |
                Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True)
            )
        qs = OrderPosition.objects.filter(
            status_q,
            order__event=self.request.event,
        ).annotate(
            last_entry=Subquery(cqs[:1].values('datetime')),
            last_exit=Subquery(cqs_exit),
            auto_checked_in=Exists(
                Checkin.objects.filter(
                    position_id=OuterRef('pk'),
                    type=Checkin.TYPE_ENTRY,
                    list_id=self.list.pk,
                    auto_checked_in=True
                )
            ),
            last_entry_source_type=Subquery(cqs[:1].values('raw_source_type'))
        ).select_related(
            'item', 'variation', 'order', 'addon_to'
        ).prefetch_related(
            Prefetch('subevent', queryset=self.request.event.subevents.all())
        )
        if self.list.subevent:
            qs = qs.filter(
                subevent=self.list.subevent
            )

        if not self.list.all_products:
            qs = qs.filter(item__in=self.list.limit_products.values_list('id', flat=True))

        if filter and self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        if 'checkin' in self.request_data and '__ALL' not in self.request_data:
            qs = qs.filter(
                id__in=self.request_data.getlist('checkin')
            )

        return qs

    @cached_property
    def filter_form(self):
        return CheckinListAttendeeFilterForm(
            data=self.request_data,
            event=self.request.event,
            list=self.list
        )


class CheckInListShow(EventPermissionRequiredMixin, PaginationMixin, CheckInListQueryMixin, ListView):
    model = Checkin
    context_object_name = 'entries'
    template_name = 'pretixcontrol/checkin/index.html'
    permission = 'can_view_orders'

    def dispatch(self, request, *args, **kwargs):
        self.list = get_object_or_404(self.request.event.checkin_lists.all(), pk=kwargs.get("list"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['media_types'] = MEDIA_TYPES
        ctx['checkinlist'] = self.list
        if self.request.event.has_subevents:
            ctx['seats'] = (
                self.list.subevent.seating_plan_id if self.list.subevent
                else self.request.event.subevents.filter(seating_plan__isnull=False).exists()
            )
        else:
            ctx['seats'] = self.request.event.seating_plan_id
        ctx['filter_form'] = self.filter_form
        for e in ctx['entries']:
            if e.last_entry:
                if isinstance(e.last_entry, str):
                    # Apparently only happens on SQLite
                    e.last_entry_aware = make_aware(dateutil.parser.parse(e.last_entry), timezone.utc)
                elif not is_aware(e.last_entry):
                    # Apparently only happens on MySQL
                    e.last_entry_aware = make_aware(e.last_entry, timezone.utc)
                else:
                    # This would be correct, so guess on which database it works… Yes, it's PostgreSQL.
                    e.last_entry_aware = e.last_entry
            if e.last_exit:
                if isinstance(e.last_exit, str):
                    # Apparently only happens on SQLite
                    e.last_exit_aware = make_aware(dateutil.parser.parse(e.last_exit), timezone.utc)
                elif not is_aware(e.last_exit):
                    # Apparently only happens on MySQL
                    e.last_exit_aware = make_aware(e.last_exit, timezone.utc)
                else:
                    # This would be correct, so guess on which database it works… Yes, it's PostgreSQL.
                    e.last_exit_aware = e.last_exit
        return ctx


class CheckInListBulkRevertConfirmView(CheckInListQueryMixin, EventPermissionRequiredMixin, TemplateView):
    template_name = "pretixcontrol/checkin/bulk_revert_confirm.html"

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(permitted_methods=["POST"])

    def post(self, request, *args, **kwargs):
        self.list = get_object_or_404(self.request.event.checkin_lists.all(), pk=kwargs.get("list"))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            cnt=self.get_queryset().count(),
            checkinlist=self.list,
        )


class CheckInListBulkActionView(CheckInListQueryMixin, EventPermissionRequiredMixin, AsyncPostView):
    permission = ('can_change_orders', 'can_checkin_orders')

    def dispatch(self, request, *args, **kwargs):
        self.list = get_object_or_404(self.request.event.checkin_lists.all(), pk=kwargs.get("list"))
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().prefetch_related(None).order_by()

    def get_error_url(self):
        return self.get_success_url(None)

    @transaction.atomic()
    def async_post(self, request, *args, **kwargs):
        self.list = get_object_or_404(request.event.checkin_lists.all(), pk=kwargs.get("list"))
        positions = self.get_queryset()
        if request.POST.get('revert') == 'true':
            if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
                raise PermissionDenied()
            for op in positions:
                if op.order.status == Order.STATUS_PAID or (
                    (self.list.include_pending or op.order.valid_if_pending) and op.order.status == Order.STATUS_PENDING
                ):
                    _, deleted = Checkin.objects.filter(position=op, list=self.list).delete()
                    if deleted:
                        op.order.log_action('pretix.event.checkin.reverted', data={
                            'position': op.id,
                            'positionid': op.positionid,
                            'list': self.list.pk,
                            'web': True
                        }, user=request.user)
                        op.order.touch()

            return 'reverted', request.POST.get('returnquery')
        else:
            t = Checkin.TYPE_EXIT if request.POST.get('checkout') == 'true' else Checkin.TYPE_ENTRY
            for op in positions:
                if op.order.status == Order.STATUS_PAID or (
                    (self.list.include_pending or op.order.valid_if_pending) and op.order.status == Order.STATUS_PENDING
                ):
                    lci = op.checkins.filter(list=self.list).first()
                    if self.list.allow_multiple_entries or t != Checkin.TYPE_ENTRY or (lci and lci.type != Checkin.TYPE_ENTRY):
                        ci = Checkin.objects.create(position=op, list=self.list, datetime=now(), type=t)
                        created = True
                    else:
                        try:
                            ci, created = Checkin.objects.get_or_create(position=op, list=self.list, defaults={
                                'datetime': now(),
                            })
                        except Checkin.MultipleObjectsReturned:
                            ci, created = Checkin.objects.filter(position=op, list=self.list).first(), False

                    op.order.log_action('pretix.event.checkin', data={
                        'position': op.id,
                        'positionid': op.positionid,
                        'first': created,
                        'forced': False,
                        'datetime': now(),
                        'type': t,
                        'list': self.list.pk,
                        'web': True
                    }, user=request.user)
                    checkin_created.send(op.order.event, checkin=ci)
            return 'checked-out' if t == Checkin.TYPE_EXIT else 'checked-in', request.POST.get('returnquery')

    def get_success_message(self, value):
        if value[0] == 'reverted':
            return _('The selected check-ins have been reverted.')
        elif value[0] == 'checked-out':
            return _('The selected tickets have been marked as checked out.')
        else:
            return _('The selected tickets have been marked as checked in.')

    def get_success_url(self, value):
        return reverse('control:event.orders.checkinlists.show', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'list': self.list.pk
        }) + ('?' + value[1] if value and value[1] else '')


class CheckinListList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = CheckinList
    context_object_name = 'checkinlists'
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/checkin/lists.html'
    ordering = ('subevent__date_from', 'name', 'pk')

    def get_queryset(self):
        qs = self.request.event.checkin_lists.select_related('subevent').prefetch_related(
            "limit_products",
        )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        clists = list(ctx['checkinlists'])

        for cl in clists:
            if cl.subevent:
                cl.subevent.event = self.request.event  # re-use same event object to make sure settings are cached
        ctx['checkinlists'] = clists

        ctx['can_change_organizer_settings'] = self.request.user.has_organizer_permission(
            self.request.organizer,
            'can_change_organizer_settings',
            self.request
        )
        ctx['filter_form'] = self.filter_form

        return ctx

    @cached_property
    def filter_form(self):
        return CheckinListFilterForm(data=self.request.GET, event=self.request.event)


class CheckinListCreate(EventPermissionRequiredMixin, CreateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def dispatch(self, request, *args, **kwargs):
        r = super().dispatch(request, *args, **kwargs)
        r['Content-Security-Policy'] = 'script-src \'unsafe-eval\''
        return r

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.checkin_lists.get(pk=self.request.GET.get("copy_from"))
            except CheckinList.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
        else:
            kwargs['instance'] = CheckinList(event=self.request.event)
        return kwargs

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new check-in list has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.checkinlist.added', user=self.request.user,
                                 data=dict(form.cleaned_data))
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class CheckinListUpdate(EventPermissionRequiredMixin, UpdateView):
    model = CheckinList
    form_class = CheckinListForm
    template_name = 'pretixcontrol/checkin/list_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def dispatch(self, request, *args, **kwargs):
        r = super().dispatch(request, *args, **kwargs)
        r['Content-Security-Policy'] = 'script-src \'unsafe-eval\''
        return r

    def get_context_data(self, **kwargs):
        return {
            'items': [
                {
                    'id': i.pk,
                    'name': str(i),
                    'variations': [
                        {
                            'id': v.pk,
                            'name': str(v.value)
                        } for v in i.variations.all()
                    ]
                } for i in self.request.event.items.filter(active=True).prefetch_related('variations')
            ],
            **super().get_context_data(),
        }

    def get_object(self, queryset=None) -> CheckinList:
        try:
            return self.request.event.checkin_lists.get(
                id=self.kwargs['list']
            )
        except CheckinList.DoesNotExist:
            raise Http404(_("The requested list does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.checkinlist.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists.edit', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'list': self.object.pk
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class CheckinListDelete(EventPermissionRequiredMixin, CompatDeleteView):
    model = CheckinList
    template_name = 'pretixcontrol/checkin/list_delete.html'
    permission = 'can_change_event_settings'
    context_object_name = 'checkinlist'

    def get_object(self, queryset=None) -> CheckinList:
        try:
            return self.request.event.checkin_lists.get(
                id=self.kwargs['list']
            )
        except CheckinList.DoesNotExist:
            raise Http404(_("The requested list does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.checkins.all().delete()
        self.object.log_action(action='pretix.event.checkinlist.deleted', user=request.user)
        self.object.delete()
        messages.success(self.request, _('The selected list has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.orders.checkinlists', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class CheckinListView(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = Checkin
    context_object_name = 'checkins'
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/checkin/checkins.html'
    ordering = ('-datetime', '-pk')

    def get_queryset(self):
        qs = Checkin.all.filter(
            list__event=self.request.event,
        ).select_related(
            'position', 'position__order', 'position__item', 'position__variation', 'position__subevent'
        ).prefetch_related(
            'list', 'gate', 'device'
        )
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    @cached_property
    def filter_form(self):
        return CheckinFilterForm(data=self.request.GET, event=self.request.event)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['filter_form'] = self.filter_form
        ctx['media_types'] = MEDIA_TYPES
        return ctx


class CheckInListSimulator(EventPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/checkin/simulator.html'
    permission = 'can_view_orders'
    form_class = CheckinListSimulatorForm

    def dispatch(self, request, *args, **kwargs):
        self.list = get_object_or_404(self.request.event.checkin_lists.all(), pk=kwargs.get("list"))
        self.result = None
        r = super().dispatch(request, *args, **kwargs)
        r['Content-Security-Policy'] = 'script-src \'unsafe-eval\''
        return r

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def get_initial(self):
        return {
            'datetime': now()
        }

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            checkinlist=self.list,
            result=self.result,
            reason_labels=dict(Checkin.REASONS),
        )

    def form_valid(self, form):
        self.result = _redeem_process(
            checkinlists=[self.list],
            raw_barcode=form.cleaned_data["raw_barcode"],
            answers_data={},
            datetime=form.cleaned_data["datetime"],
            force=False,
            checkin_type=form.cleaned_data["checkin_type"],
            ignore_unpaid=form.cleaned_data["ignore_unpaid"],
            untrusted_input=True,
            user=self.request.user,
            auth=None,
            expand=[],
            nonce=secrets.token_hex(12),
            pdf_data=False,
            questions_supported=form.cleaned_data["questions_supported"],
            canceled_supported=False,
            request=self.request,  # this is not clean, but we need it in the serializers for URL generation
            legacy_url_support=False,
            simulate=True,
            gate=form.cleaned_data.get("gate"),
        ).data

        if self.result.get("position"):
            op = OrderPosition.objects.get(pk=self.result["position"]["id"])
            self.result["position_object"] = op

        if form.cleaned_data["checkin_type"] == Checkin.TYPE_ENTRY and self.list.rules and self.result.get("position")\
                and (self.result["status"] in ("ok", "incomplete") or self.result["reason"] == "rules"):
            rule_data = LazyRuleVars(op, self.list, form.cleaned_data["datetime"], form.cleaned_data.get("gate"))
            rule_graph = _logic_annotate_for_graphic_explain(self.list.rules, op.subevent or self.list.event, rule_data,
                                                             form.cleaned_data["datetime"])
            self.result["rule_graph"] = rule_graph

        if self.result.get("questions"):
            for q in self.result["questions"]:
                q["question"] = LazyI18nString(q["question"])
        return self.get(self.request, self.args, self.kwargs)


class CheckInResetView(CheckInListQueryMixin, EventPermissionRequiredMixin, AsyncFormView):
    form_class = CheckinResetForm
    permission = "can_change_orders"
    template_name = "pretixcontrol/checkin/reset.html"

    def get_error_url(self, *args):
        return reverse(
            "control:event.orders.checkinlists",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.organizer.slug,
            },
        )

    def get_success_url(self, *args):
        return reverse(
            "control:event.orders.checkinlists",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.organizer.slug,
            },
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['checkins'] = Checkin.all.filter(list__event=self.request.event).count()
        ctx['printlogs'] = PrintLog.objects.filter(position__order__event=self.request.event).count()
        return ctx

    def async_form_valid(self, task, form):
        with transaction.atomic():
            qs = Checkin.all.filter(list__event=self.request.event).select_related("position", "position__order")
            logentries = []
            for ci in qs:
                if ci.position:
                    logentries.append(ci.position.order.log_action('pretix.event.checkin.reverted', data={
                        'position': ci.position.id,
                        'positionid': ci.position.positionid,
                        'list': ci.list_id,
                        'web': True
                    }, user=self.request.user, save=False))

            Order.objects.filter(pk__in=qs.values_list("position__order_id", flat=True)).update(last_modified=now())
            qs.delete()
            LogEntry.objects.bulk_create(logentries)

            pl = PrintLog.objects.filter(position__order__event=self.request.event)
            pl.delete()
            self.request.event.log_action('pretix.event.checkin.reset', user=self.request.user)
            self.request.event.cache.clear()
