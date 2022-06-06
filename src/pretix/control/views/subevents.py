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
# This file contains Apache-licensed contributions copyrighted by: Aiman Parvaiz
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
from collections import defaultdict
from datetime import datetime, time, timedelta

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule, rruleset
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import connections, transaction
from django.db.models import Count, F, Prefetch, ProtectedError
from django.db.models.functions import Coalesce, TruncDate, TruncTime
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.formats import get_format
from django.utils.functional import cached_property
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, FormView, ListView, UpdateView,
)

from pretix.base.models import CartPosition, LogEntry
from pretix.base.models.checkin import CheckinList
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models.items import (
    ItemVariation, Quota, SubEventItem, SubEventItemVariation,
)
from pretix.base.reldate import RelativeDate, RelativeDateWrapper
from pretix.base.services import tickets
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.views.tasks import AsyncFormView
from pretix.control.forms.checkin import SimpleCheckinListForm
from pretix.control.forms.filter import SubEventFilterForm
from pretix.control.forms.item import QuotaForm
from pretix.control.forms.subevents import (
    BulkSubEventItemForm, BulkSubEventItemVariationForm, CheckinListFormSet,
    QuotaFormSet, RRuleFormSet, SubEventBulkEditForm, SubEventBulkForm,
    SubEventForm, SubEventItemForm, SubEventItemVariationForm,
    SubEventMetaValueForm, TimeFormSet,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.signals import subevent_forms
from pretix.control.views import PaginationMixin
from pretix.control.views.event import MetaDataEditorMixin
from pretix.helpers import GroupConcat
from pretix.helpers.models import modelcopy


class SubEventQueryMixin:

    @cached_property
    def request_data(self):
        if self.request.method == "POST":
            return self.request.POST
        return self.request.GET

    def get_queryset(self, list=False):
        qs = self.request.event.subevents
        if list:
            qs = qs.prefetch_related(
                Prefetch('quotas',
                         queryset=self.request.event.quotas.annotate(s=Coalesce(F('size'), 0)).order_by('-s'),
                         to_attr='first_quotas')
            )
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        if 'subevent' in self.request_data and '__ALL' not in self.request_data:
            qs = qs.filter(
                id__in=self.request_data.getlist('subevent')
            )

        return qs

    @cached_property
    def filter_form(self):
        return SubEventFilterForm(data=self.request_data, prefix='filter')


class SubEventList(EventPermissionRequiredMixin, PaginationMixin, SubEventQueryMixin, ListView):
    model = SubEvent
    context_object_name = 'subevents'
    template_name = 'pretixcontrol/subevents/index.html'
    permission = 'can_change_settings'

    def get_queryset(self):
        return super().get_queryset(True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form

        quotas = []
        for s in ctx['subevents']:
            s.first_quotas = s.first_quotas[:4]
            quotas += list(s.first_quotas)

        qa = QuotaAvailability(early_out=False)
        for q in quotas:
            qa.queue(q)
        qa.compute()

        for q in quotas:
            q.cached_avail = qa.results[q]
            q.cached_availability_paid_orders = qa.count_paid_orders.get(q, 0)
            if q.size is not None:
                q.percent_paid = min(
                    100,
                    round(q.cached_availability_paid_orders / q.size * 100) if q.size > 0 else 100
                )
        return ctx


class SubEventDelete(EventPermissionRequiredMixin, DeleteView):
    model = SubEvent
    template_name = 'pretixcontrol/subevents/delete.html'
    permission = 'can_change_settings'
    context_object_name = 'subevents'

    def get_object(self, queryset=None) -> SubEvent:
        try:
            return self.request.event.subevents.get(
                id=self.kwargs['subevent']
            )
        except SubEvent.DoesNotExist:
            raise Http404(pgettext_lazy("subevent", "The requested date does not exist."))

    def get(self, request, *args, **kwargs):
        if not self.get_object().allow_delete():
            messages.error(request, pgettext_lazy('subevent', 'A date can not be deleted if orders already have been '
                                                              'placed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if not self.object.allow_delete():
            messages.error(request, pgettext_lazy('subevent', 'A date can not be deleted if orders already have been '
                                                              'placed.'))
            return HttpResponseRedirect(self.get_success_url())
        else:
            self.object.log_action('pretix.subevent.deleted', user=self.request.user)
            CartPosition.objects.filter(addon_to__subevent=self.object).delete()
            self.object.cartposition_set.all().delete()
            self.object.delete()
            messages.success(request, pgettext_lazy('subevent', 'The selected date has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class SubEventEditorMixin(MetaDataEditorMixin):
    meta_form = SubEventMetaValueForm
    meta_model = SubEventMetaValue
    itemformclass = SubEventItemForm
    itemvarformclass = SubEventItemVariationForm

    @cached_property
    def plugin_forms(self):
        forms = []
        for rec, resp in subevent_forms.send(sender=self.request.event, subevent=self.object, request=self.request,
                                             copy_from=self.copy_from):
            if isinstance(resp, (list, tuple)):
                forms.extend(resp)
            else:
                forms.append(resp)
        return forms

    def _make_meta_form(self, p, val_instances):
        if not hasattr(self, '_default_meta'):
            self._default_meta = self.request.event.meta_data

        return self.meta_form(
            prefix='prop-{}'.format(p.pk),
            property=p,
            disabled=(
                p.protected and
                not self.request.user.has_organizer_permission(self.request.organizer, 'can_change_organizer_settings', request=self.request)
            ),
            default=self._default_meta.get(p.name, ''),
            instance=val_instances.get(p.pk, self.meta_model(property=p, subevent=self.object)),
            data=(self.request.POST if self.request.method == "POST" else None)
        )

    @cached_property
    def cl_formset(self):
        extra = 0
        kwargs = {}

        if self.copy_from and self.request.method != "POST":
            kwargs['initial'] = [
                {
                    'name': cl.name,
                    'all_products': cl.all_products,
                    'limit_products': cl.limit_products.all(),
                    'include_pending': cl.include_pending,
                } for cl in self.copy_from.checkinlist_set.prefetch_related('limit_products')
            ]
            extra = len(kwargs['initial'])
        elif not self.object and self.request.method != "POST":
            kwargs['initial'] = [
                {
                    'name': '',
                    'all_products': True,
                    'include_pending': False,
                }
            ]
            extra = 0

        formsetclass = inlineformset_factory(
            SubEvent, CheckinList,
            form=SimpleCheckinListForm, formset=CheckinListFormSet,
            can_order=False, can_delete=True, extra=extra,
        )
        if self.object:
            kwargs['queryset'] = self.object.checkinlist_set.prefetch_related('limit_products')

        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            instance=self.object,
                            event=self.request.event, **kwargs)

    @cached_property
    def formset(self):
        kwargs = {}

        if self.copy_from and self.request.method != "POST":
            kwargs['initial'] = [
                {
                    'size': q.size,
                    'name': q.name,
                    'release_after_exit': q.release_after_exit,
                    'ignore_for_event_availability': q.ignore_for_event_availability,
                    'itemvars': [str(i.pk) for i in q.items.all()] + [
                        '{}-{}'.format(v.item_id, v.pk) for v in q.variations.all()
                    ]
                } for q in self.copy_from.quotas.prefetch_related('items', 'variations')
            ]
            extra = len(kwargs['initial']) - 1
        else:
            kwargs['initial'] = [
                {
                    'name': _('Tickets'),
                }
            ]
            extra = 0

        formsetclass = inlineformset_factory(
            SubEvent, Quota,
            form=QuotaForm, formset=QuotaFormSet, min_num=1, validate_min=True,
            can_order=False, can_delete=True, extra=extra,
        )
        if self.object:
            kwargs['queryset'] = self.object.quotas.prefetch_related('items', 'variations')

        return formsetclass(
            self.request.POST if self.request.method == "POST" else None,
            instance=self.object,
            event=self.request.event, **kwargs
        )

    def save_cl_formset(self, obj):
        for form in self.cl_formset.initial_forms:
            if form in self.cl_formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.checkins.all().delete()
                form.instance.log_action(action='pretix.event.checkinlist.deleted', user=self.request.user)
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.subevent = obj
                form.instance.event = obj.event
                form.save()
                change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                change_data['id'] = form.instance.pk
                form.instance.log_action(
                    'pretix.event.checkinlist.changed', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )

        for form in self.cl_formset.extra_forms:
            if not form.has_changed():
                continue
            if self.formset._should_delete_form(form):
                continue
            form.instance.subevent = obj
            form.instance.event = obj.event
            form.save()
            change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
            change_data['id'] = form.instance.pk
            form.instance.log_action(action='pretix.event.checkinlist.added', user=self.request.user, data=change_data)

    def save_formset(self, obj):
        for form in self.formset.initial_forms:
            if form in self.formset.deleted_forms:
                if not form.instance.pk:
                    continue
                form.instance.log_action(action='pretix.event.quota.deleted', user=self.request.user)
                obj.log_action('pretix.subevent.quota.deleted', user=self.request.user, data={
                    'id': form.instance.pk
                })
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.question = obj
                form.save()
                change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                change_data['id'] = form.instance.pk
                obj.log_action(
                    'pretix.subevent.quota.changed', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )
                form.instance.log_action(
                    'pretix.event.quota.changed', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )

        for form in self.formset.extra_forms:
            if not form.has_changed():
                continue
            if self.formset._should_delete_form(form):
                continue
            form.instance.subevent = obj
            form.instance.event = obj.event
            form.save()
            change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
            change_data['id'] = form.instance.pk
            form.instance.log_action(action='pretix.event.quota.added', user=self.request.user, data=change_data)
            obj.log_action('pretix.subevent.quota.added', user=self.request.user, data=change_data)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        ctx['cl_formset'] = self.cl_formset
        ctx['itemvar_forms'] = self.itemvar_forms
        ctx['meta_forms'] = self.meta_forms
        ctx['plugin_forms'] = self.plugin_forms
        return ctx

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and (not getattr(self, 'object', None) or not self.object.pk):
            try:
                return self.request.event.subevents.get(pk=self.request.GET.get("copy_from"))
            except SubEvent.DoesNotExist:
                pass

    @cached_property
    def itemvar_forms(self):
        se_item_instances = {
            sei.item_id: sei for sei in SubEventItem.objects.filter(subevent=self.object)
        }
        se_var_instances = {
            sei.variation_id: sei for sei in SubEventItemVariation.objects.filter(subevent=self.object)
        }

        if self.copy_from:
            se_item_instances = {
                sei.item_id: SubEventItem(
                    item=sei.item, price=sei.price, disabled=sei.disabled,
                    available_from=sei.available_from, available_until=sei.available_until
                )
                for sei in SubEventItem.objects.filter(subevent=self.copy_from).select_related('item')
            }
            se_var_instances = {
                sei.variation_id: SubEventItemVariation(
                    variation=sei.variation, price=sei.price, disabled=sei.disabled,
                    available_from=sei.available_from, available_until=sei.available_until
                )
                for sei in SubEventItemVariation.objects.filter(subevent=self.copy_from).select_related('variation')
            }

        formlist = []
        for i in self.request.event.items.filter(active=True).prefetch_related('variations'):
            if i.has_variations:
                for v in i.variations.all():
                    inst = se_var_instances.get(v.pk) or SubEventItemVariation(subevent=self.object, variation=v)
                    formlist.append(self.itemvarformclass(
                        prefix='itemvar-{}'.format(v.pk),
                        item=i, variation=v,
                        instance=inst,
                        data=(self.request.POST if self.request.method == "POST" else None)
                    ))
            else:
                inst = se_item_instances.get(i.pk) or SubEventItem(subevent=self.object, item=i)
                formlist.append(self.itemformclass(
                    prefix='item-{}'.format(i.pk),
                    item=i,
                    instance=inst,
                    data=(self.request.POST if self.request.method == "POST" else None)
                ))
        return formlist

    def is_valid(self, form):
        return form.is_valid() and all([f.is_valid() for f in self.itemvar_forms]) and self.formset.is_valid() and (
            all([f.is_valid() for f in self.meta_forms])
        ) and self.cl_formset.is_valid() and all(f.is_valid() for f in self.plugin_forms)


class SubEventUpdate(EventPermissionRequiredMixin, SubEventEditorMixin, UpdateView):
    model = SubEvent
    template_name = 'pretixcontrol/subevents/detail.html'
    permission = 'can_change_settings'
    context_object_name = 'subevent'
    form_class = SubEventForm

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if self.is_valid(form):
            r = self.form_valid(form)
            return r
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return self.form_invalid(form)

    def get_object(self, queryset=None) -> SubEvent:
        try:
            return self.request.event.subevents.get(
                id=self.kwargs['subevent']
            )
        except SubEvent.DoesNotExist:
            raise Http404(pgettext_lazy("subevent", "The requested date does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        self.save_formset(self.object)
        self.save_cl_formset(self.object)
        self.save_meta()

        for f in self.itemvar_forms:
            f.save()
            # TODO: LogEntry?

        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed() or any(f.has_changed() for f in self.plugin_forms):
            data = {
                k: form.cleaned_data.get(k) for k in form.changed_data
            }
            for f in self.plugin_forms:
                data.update({
                    k: (f.cleaned_data.get(k).name
                        if isinstance(f.cleaned_data.get(k), File)
                        else f.cleaned_data.get(k))
                    for k in f.changed_data
                })
            self.object.log_action(
                'pretix.subevent.changed', user=self.request.user, data=data
            )
        for f in self.plugin_forms:
            f.subevent = self.object
            f.save()
        tickets.invalidate_cache.apply_async(kwargs={'event': self.request.event.pk})
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }) + ('?' + self.request.GET.get('returnto') if 'returnto' in self.request.GET else '')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs


class SubEventCreate(SubEventEditorMixin, EventPermissionRequiredMixin, CreateView):
    model = SubEvent
    template_name = 'pretixcontrol/subevents/detail.html'
    permission = 'can_change_settings'
    context_object_name = 'subevent'
    form_class = SubEventForm

    def get_initial(self):
        return {
            'active': True,
        }

    def post(self, request, *args, **kwargs):
        self.object = SubEvent(event=self.request.event)
        form = self.get_form()
        if self.is_valid(form):
            return self.form_valid(form)
        return self.form_invalid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        initial = kwargs.get('initial', {})
        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
        else:
            kwargs['instance'] = SubEvent(event=self.request.event)
            initial['location'] = self.request.event.location
            initial['geo_lat'] = self.request.event.geo_lat
            initial['geo_lon'] = self.request.event.geo_lon
        kwargs['initial'] = initial
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, pgettext_lazy('subevent', 'The new date has been created.'))
        ret = super().form_valid(form)
        self.object = form.instance

        data = dict(form.cleaned_data)
        for f in self.plugin_forms:
            data.update({
                k: (f.cleaned_data.get(k).name
                    if isinstance(f.cleaned_data.get(k), File)
                    else f.cleaned_data.get(k))
                for k in f.cleaned_data
            })
        form.instance.log_action('pretix.subevent.added', data=dict(data), user=self.request.user)

        self.save_formset(form.instance)
        self.save_cl_formset(form.instance)
        for f in self.itemvar_forms:
            f.instance.subevent = form.instance
            f.save()
        for f in self.meta_forms:
            f.instance.subevent = form.instance
        self.save_meta()
        for f in self.plugin_forms:
            f.subevent = form.instance
            f.save()
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    @cached_property
    def meta_forms(self):
        def clone(o):
            o = copy.copy(o)
            o.pk = None
            return o

        if self.copy_from:
            val_instances = {
                v.property_id: clone(v) for v in self.copy_from.meta_values.all()
            }
        else:
            val_instances = {}

        formlist = []

        for p in self.request.organizer.meta_properties.all():
            formlist.append(self._make_meta_form(p, val_instances))
        return formlist


class SubEventBulkAction(SubEventQueryMixin, EventPermissionRequiredMixin, View):
    permission = 'can_change_settings'

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'disable':
            for obj in self.get_queryset():
                obj.log_action(
                    'pretix.subevent.changed', user=self.request.user, data={
                        'active': False
                    }
                )
                obj.active = False
                obj.save(update_fields=['active'])
            messages.success(request, pgettext_lazy('subevent', 'The selected dates have been disabled.'))
        elif request.POST.get('action') == 'enable':
            for obj in self.get_queryset():
                obj.log_action(
                    'pretix.subevent.changed', user=self.request.user, data={
                        'active': True
                    }
                )
                obj.active = True
                obj.save(update_fields=['active'])
            messages.success(request, pgettext_lazy('subevent', 'The selected dates have been enabled.'))
        elif request.POST.get('action') == 'delete':
            return render(request, 'pretixcontrol/subevents/delete_bulk.html', {
                'allowed': self.get_queryset().filter(orderposition__isnull=True),
                'forbidden': self.get_queryset().filter(orderposition__isnull=False).distinct(),
            })
        elif request.POST.get('action') == 'delete_confirm':
            for obj in self.get_queryset():
                try:
                    if not obj.allow_delete():
                        raise ProtectedError('only deactivate', [obj])
                    CartPosition.objects.filter(addon_to__subevent=obj).delete()
                    obj.cartposition_set.all().delete()
                    obj.log_action('pretix.subevent.deleted', user=self.request.user)
                    obj.delete()
                except ProtectedError:
                    obj.log_action(
                        'pretix.subevent.changed', user=self.request.user, data={
                            'active': False
                        }
                    )
                    obj.active = False
                    obj.save(update_fields=['active'])
            messages.success(request, pgettext_lazy('subevent', 'The selected dates have been deleted or disabled.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class SubEventBulkCreate(SubEventEditorMixin, EventPermissionRequiredMixin, AsyncFormView):
    model = SubEvent
    template_name = 'pretixcontrol/subevents/bulk.html'
    permission = 'can_change_settings'
    context_object_name = 'subevent'
    form_class = SubEventBulkForm
    itemformclass = BulkSubEventItemForm
    itemvarformclass = BulkSubEventItemVariationForm

    def dispatch(self, request, *args, **kwargs):
        self.object = SubEvent(event=self.request.event)
        return super().dispatch(request, *args, **kwargs)

    def is_valid(self, form):
        return self.rrule_formset.is_valid() and self.time_formset.is_valid() and super().is_valid(form)

    def get_success_url(self, value) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_error_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @cached_property
    def rrule_formset(self):
        return RRuleFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            prefix='rruleformset'
        )

    @cached_property
    def time_formset(self):
        return TimeFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            prefix='timeformset'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['rrule_formset'] = self.rrule_formset
        ctx['time_formset'] = self.time_formset

        tf = get_format('TIME_INPUT_FORMATS')[0]
        ctx['time_begin_sample'] = time(9, 0, 0).strftime(tf)
        ctx['time_end_sample'] = time(18, 0, 0).strftime(tf)
        return ctx

    @cached_property
    def meta_forms(self):
        def clone(o):
            o = copy.copy(o)
            o.pk = None
            return o

        if self.copy_from:
            val_instances = {
                v.property_id: clone(v) for v in self.copy_from.meta_values.all()
            }
        else:
            val_instances = {}

        formlist = []

        for p in self.request.organizer.meta_properties.all():
            formlist.append(self._make_meta_form(p, val_instances))
        return formlist

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        initial = {
            'active': True,
        }
        kwargs['event'] = self.request.event
        tz = self.request.event.timezone
        if self.copy_from:
            i = copy.copy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
            initial['time_from'] = i.date_from.astimezone(tz).time()
            initial['time_to'] = i.date_to.astimezone(tz).time() if i.date_to else None
            initial['time_admission'] = i.date_admission.astimezone(tz).time() if i.date_admission else None
            initial['rel_presale_start'] = RelativeDateWrapper(RelativeDate(
                days_before=(i.date_from.astimezone(tz).date() - i.presale_start.astimezone(tz).date()).days,
                base_date_name='date_from',
                time=i.presale_start.astimezone(tz).time(),
                minutes_before=None
            )) if i.presale_start else None
            initial['rel_presale_end'] = RelativeDateWrapper(RelativeDate(
                days_before=(i.date_from.astimezone(tz).date() - i.presale_end.astimezone(tz).date()).days,
                base_date_name='date_from',
                time=i.presale_end.astimezone(tz).time(),
                minutes_before=None
            )) if i.presale_end else None
        else:
            kwargs['instance'] = SubEvent(event=self.request.event)
            initial['location'] = self.request.event.location
            initial['geo_lat'] = self.request.event.geo_lat
            initial['geo_lon'] = self.request.event.geo_lon
        kwargs['initial'] = initial
        return kwargs

    def get_async_form_kwargs(self, form_kwargs, organizer=None, event=None):
        form_kwargs['event'] = event
        form_kwargs['instance'] = SubEvent(event=event)
        return form_kwargs

    def get_times(self):
        times = []
        for f in self.time_formset:
            if f in self.time_formset.deleted_forms or not f.cleaned_data.get('time_from'):
                continue
            times.append(f.cleaned_data)
        return times

    def get_rrule_set(self):
        s = rruleset()
        for f in self.rrule_formset:
            if f in self.rrule_formset.deleted_forms:
                continue

            rule_kwargs = {}
            rule_kwargs['dtstart'] = f.cleaned_data['dtstart']
            rule_kwargs['interval'] = f.cleaned_data['interval']

            if f.cleaned_data['freq'] == 'yearly':
                freq = YEARLY
                if f.cleaned_data['yearly_same'] == "off":
                    rule_kwargs['bysetpos'] = int(f.cleaned_data['yearly_bysetpos'])
                    rule_kwargs['byweekday'] = f.parse_weekdays(f.cleaned_data['yearly_byweekday'])
                    rule_kwargs['bymonth'] = int(f.cleaned_data['yearly_bymonth'])

            elif f.cleaned_data['freq'] == 'monthly':
                freq = MONTHLY

                if f.cleaned_data['monthly_same'] == "off":
                    rule_kwargs['bysetpos'] = int(f.cleaned_data['monthly_bysetpos'])
                    rule_kwargs['byweekday'] = f.parse_weekdays(f.cleaned_data['monthly_byweekday'])
            elif f.cleaned_data['freq'] == 'weekly':
                freq = WEEKLY

                if f.cleaned_data['weekly_byweekday']:
                    rule_kwargs['byweekday'] = [f.parse_weekdays(a) for a in f.cleaned_data['weekly_byweekday']]

            elif f.cleaned_data['freq'] == 'daily':
                freq = DAILY

            if f.cleaned_data['end'] == 'count':
                rule_kwargs['count'] = f.cleaned_data['count']
            else:
                rule_kwargs['until'] = f.cleaned_data['until']

            if f.cleaned_data['exclude']:
                s.exrule(rrule(freq, **rule_kwargs))
            else:
                s.rrule(rrule(freq, **rule_kwargs))

        return s

    @transaction.atomic
    def async_form_valid(self, task, form):
        self.object = SubEvent(event=self.request.event)
        if not self.is_valid(form):
            raise ValidationError('Invalid submission')

        def set_progress(percent):
            if not task.request.called_directly:
                task.update_state(
                    state='PROGRESS',
                    meta={'value': percent}
                )

        set_progress(0)

        tz = self.request.event.timezone
        subevents = []
        for rdate in self.get_rrule_set():
            for t in self.get_times():
                se = copy.copy(form.instance)

                se.date_from = make_aware(datetime.combine(rdate, t['time_from']), tz, is_dst=False)

                if t.get('time_to'):
                    se.date_to = (
                        make_aware(datetime.combine(rdate, t['time_to']), tz, is_dst=False)
                        if t.get('time_to') > t.get('time_from')
                        else make_aware(datetime.combine(rdate + timedelta(days=1), t['time_to']), tz, is_dst=False)
                    )
                else:
                    se.date_to = None
                se.date_admission = (
                    make_aware(datetime.combine(rdate, t['time_admission'].replace(fold=1)), tz, is_dst=False)
                    if t.get('time_admission')
                    else None
                )
                se.presale_start = (
                    form.cleaned_data['rel_presale_start'].datetime(se)
                    if form.cleaned_data.get('rel_presale_start')
                    else None
                )
                se.presale_end = (
                    form.cleaned_data['rel_presale_end'].datetime(se)
                    if form.cleaned_data.get('rel_presale_end')
                    else None
                )
                subevents.append(se)

            if len(subevents) > 100_000:
                raise ValidationError(_('Please do not create more than 100.000 dates at once.'))

        for i, se in enumerate(subevents):
            se.save(clear_cache=False)
            if i % 100 == 0:
                set_progress(10 * i / len(subevents))

        set_progress(10)

        data = dict(form.cleaned_data)
        for f in self.plugin_forms:
            data.update({
                k: (f.cleaned_data.get(k).name
                    if isinstance(f.cleaned_data.get(k), File)
                    else f.cleaned_data.get(k))
                for k in f.cleaned_data
            })
        log_entries = []
        for se in subevents:
            log_entries.append(se.log_action('pretix.subevent.added', data=data, user=self.request.user, save=False))

        to_save = []
        for f in self.meta_forms:
            if f.cleaned_data.get('value'):
                for se in subevents:
                    i = copy.copy(f.instance)
                    i.pk = None
                    i.subevent = se
                    to_save.append(i)
        SubEventMetaValue.objects.bulk_create(to_save)

        set_progress(20)

        to_save_items = []
        to_save_variations = []
        for f in self.itemvar_forms:
            for i, se in enumerate(subevents):
                i = copy.copy(f.instance)
                i.pk = None
                i.subevent = se

                i.available_from = (
                    f.cleaned_data['rel_available_from'].datetime(se)
                    if f.cleaned_data.get('rel_available_from')
                    else None
                )
                i.available_until = (
                    f.cleaned_data['rel_available_until'].datetime(se)
                    if f.cleaned_data.get('rel_available_until')
                    else None
                )

                if isinstance(i, SubEventItem):
                    to_save_items.append(i)
                else:
                    to_save_variations.append(i)

        SubEventItem.objects.bulk_create(to_save_items)
        set_progress(30)
        SubEventItemVariation.objects.bulk_create(to_save_variations)
        set_progress(40)

        to_save_items = []
        to_save_variations = []
        for k, f in enumerate(self.formset.forms):
            if self.formset._should_delete_form(f) or not f.has_changed():
                continue

            change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
            for j, se in enumerate(subevents):
                i = copy.copy(f.instance)
                i.pk = None
                i.subevent = se
                i.event = se.event
                i.save(clear_cache=False)
                selected_items = set(list(self.request.event.items.filter(id__in=[
                    i.split('-')[0] for i in f.cleaned_data.get('itemvars', [])
                ])))
                selected_variations = list(ItemVariation.objects.filter(item__event=self.request.event, id__in=[
                    i.split('-')[1] for i in f.cleaned_data.get('itemvars', []) if '-' in i
                ]))
                for _i in selected_items:
                    to_save_items.append(Quota.items.through(quota_id=i.pk, item_id=_i.pk))
                for _i in selected_variations:
                    to_save_variations.append(Quota.variations.through(quota_id=i.pk, itemvariation_id=_i.pk))

                change_data['id'] = i.pk
                log_entries.append(
                    i.log_action(action='pretix.event.quota.added', user=self.request.user,
                                 data=change_data, save=False)
                )
                log_entries.append(
                    se.log_action('pretix.subevent.quota.added', user=self.request.user, data=change_data, save=False)
                )

                if j % 100 == 0:
                    set_progress(50 + 10 * (j + k * len(subevents)) / (len(self.formset.forms) + len(subevents)))
        Quota.items.through.objects.bulk_create(to_save_items)
        set_progress(60)
        Quota.variations.through.objects.bulk_create(to_save_variations)
        set_progress(70)

        to_save_products = []
        for f in self.cl_formset.forms:
            if self.cl_formset._should_delete_form(f) or not f.has_changed():
                continue
            change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
            for se in subevents:
                i = copy.copy(f.instance)
                i.subevent = se
                i.event = se.event
                i.save()
                for _i in f.cleaned_data.get('limit_products', []):
                    to_save_products.append(CheckinList.limit_products.through(checkinlist_id=i.pk, item_id=_i.pk))

                change_data['id'] = i.pk
                log_entries.append(
                    i.log_action(action='pretix.event.checkinlist.added', user=self.request.user, data=change_data,
                                 save=False)
                )
        CheckinList.limit_products.through.objects.bulk_create(to_save_products)
        set_progress(80)

        for f in self.plugin_forms:
            f.is_valid()
            for se in subevents:
                f.subevent = se
                f.save()
        set_progress(90)

        if connections['default'].features.can_return_rows_from_bulk_insert:
            LogEntry.objects.bulk_create(log_entries)
            LogEntry.bulk_postprocess(log_entries)
        else:
            for le in log_entries:
                le.save()
            LogEntry.bulk_postprocess(log_entries)

        self.request.event.cache.clear()
        return len(subevents)

    def get_success_message(self, value):
        return pgettext_lazy('subevent', '{} new dates have been created.').format(value)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        self.object = SubEvent(event=self.request.event)

        if self.is_valid(form):
            return self.form_valid(form)

        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return self.form_invalid(form)


class SubEventBulkEdit(SubEventQueryMixin, EventPermissionRequiredMixin, FormView):
    permission = 'can_change_settings'
    form_class = SubEventBulkEditForm
    template_name = 'pretixcontrol/subevents/bulk_edit.html'
    context_object_name = 'subevent'

    def get_queryset(self):
        return super().get_queryset().prefetch_related(None).order_by()

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get(self, request, *args, **kwargs):
        return HttpResponse(status=405)

    @cached_property
    def cached_num(self):
        return self.get_queryset().count()

    itemformclass = SubEventItemForm
    itemvarformclass = SubEventItemVariationForm

    @cached_property
    def itemvar_forms(self):
        matches = defaultdict(list)
        for sei in SubEventItem.objects.filter(
            subevent__in=self.get_queryset()
        ).order_by().values('item', 'price', 'disabled', 'available_from', 'available_until').annotate(c=Count('*')):
            matches['item', sei['item']].append(sei)
        for sei in SubEventItemVariation.objects.filter(
            subevent__in=self.get_queryset()
        ).order_by().values('variation', 'price', 'disabled', 'available_from', 'available_until').annotate(c=Count('*')):
            matches['variation', sei['variation']].append(sei)
        total = self.cached_num

        formlist = []
        for i in self.request.event.items.filter(active=True).prefetch_related('variations'):
            if i.has_variations:
                for v in i.variations.all():
                    m = matches['variation', v.pk]
                    if m and len(m) == 1 and m[0]['c'] == total:
                        inst = SubEventItemVariation(
                            variation=v, disabled=m[0]['disabled'], price=m[0]['price'],
                            available_from=m[0]['available_from'], available_until=m[0]['available_until']
                        )
                    else:
                        inst = SubEventItemVariation(variation=v)
                    formlist.append(self.itemvarformclass(
                        prefix='itemvar-{}'.format(v.pk),
                        item=i, variation=v,
                        instance=inst,
                        data=(self.request.POST if self.is_submitted else None)
                    ))
            else:
                m = matches['item', i.pk]
                if m and len(m) == 1 and m[0]['c'] == total:
                    inst = SubEventItem(
                        item=i, disabled=m[0]['disabled'], price=m[0]['price'],
                        available_from=m[0]['available_from'], available_until=m[0]['available_until']
                    )
                else:
                    inst = SubEventItem(item=i)
                formlist.append(self.itemformclass(
                    prefix='item-{}'.format(i.pk),
                    item=i,
                    instance=inst,
                    data=(self.request.POST if self.is_submitted else None)
                ))
        return formlist

    @cached_property
    def meta_forms(self):
        matches = defaultdict(list)
        for smv in SubEventMetaValue.objects.filter(
            subevent__in=self.get_queryset()
        ).order_by().values('property', 'value').annotate(c=Count('*')):
            matches[smv['property']].append(smv)
        total = self.cached_num

        formlist = []

        if not hasattr(self, '_default_meta'):
            self._default_meta = self.request.event.meta_data

        for p in self.request.organizer.meta_properties.all():
            inst = SubEventMetaValue(property=p)
            if len(matches[p.id]) == 1 and matches[p.id][0]['c'] == total:
                inst.value = matches[p.id][0]['value']
            formlist.append(SubEventMetaValueForm(
                prefix='prop-{}'.format(p.pk),
                property=p,
                default=self._default_meta.get(p.name, ''),
                instance=inst,
                data=(self.request.POST if self.is_submitted else None)
            ))
        return formlist

    @cached_property
    def quota_formset(self):
        extra = 0
        kwargs = {}

        if self.sampled_quotas is not None:
            kwargs['instance'] = self.get_queryset()[0]

        formsetclass = inlineformset_factory(
            SubEvent, Quota,
            form=QuotaForm, formset=QuotaFormSet, min_num=0, validate_min=False,
            can_order=False, can_delete=True, extra=extra,
        )
        return formsetclass(
            self.request.POST if self.is_submitted else None,
            event=self.request.event, **kwargs
        )

    @cached_property
    def list_formset(self):
        extra = 0
        kwargs = {}

        if self.sampled_lists is None:
            return None
        kwargs['instance'] = self.get_queryset()[0]

        formsetclass = inlineformset_factory(
            SubEvent, CheckinList,
            form=SimpleCheckinListForm, formset=CheckinListFormSet, min_num=0, validate_min=False,
            can_order=False, can_delete=True, extra=extra,
        )
        return formsetclass(
            self.request.POST if self.is_submitted else None,
            event=self.request.event, **kwargs
        )

    def save_list_formset(self, log_entries):
        if self.sampled_lists is None or not self.list_formset.has_changed():
            return
        qidx = 0
        subevents = list(self.get_queryset().prefetch_related('checkinlist_set'))
        to_save_products = []
        to_save_gates = []

        for f in self.list_formset.forms:
            if self.list_formset._should_delete_form(f) and f in self.list_formset.extra_forms:
                continue

            if self.list_formset._should_delete_form(f):
                for se in subevents:
                    q = list(se.checkinlist_set.all())[qidx]
                    log_entries += [
                        q.log_action(action='pretix.event.checkinlist.deleted', user=self.request.user, save=False),
                    ]
                    q.delete()
            elif f in self.list_formset.extra_forms:
                change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
                for se in subevents:
                    q = copy.copy(f.instance)
                    q.pk = None
                    q.subevent = se
                    q.event = self.request.event
                    q.save()
                    for _i in f.cleaned_data.get('limit_products', []):
                        to_save_products.append(CheckinList.limit_products.through(checkinlist_id=q.pk, item_id=_i.pk))
                    for _i in f.cleaned_data.get('gates', []):
                        to_save_gates.append(CheckinList.gates.through(checkinlist_id=q.pk, gate_id=_i.pk))
                    change_data['id'] = q.pk
                    log_entries.append(
                        q.log_action(action='pretix.event.checkinlist.added', user=self.request.user,
                                     data=change_data, save=False)
                    )
            else:
                if f.changed_data:
                    change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
                    for se in subevents:
                        q = list(se.checkinlist_set.all())[qidx]
                        for fname in ('name', 'all_products', 'include_pending', 'allow_entry_after_exit'):
                            setattr(q, fname, f.cleaned_data.get(fname))
                        q.save()
                        if 'limit_products' in f.changed_data:
                            q.limit_products.set(f.cleaned_data.get('limit_products', []))
                        if 'gates' in f.changed_data:
                            q.gates.set(f.cleaned_data.get('gates', []))
                        log_entries.append(
                            q.log_action(action='pretix.event.checkinlist.changed', user=self.request.user,
                                         data=change_data, save=False)
                        )
            qidx += 1
        if to_save_products:
            CheckinList.limit_products.through.objects.bulk_create(to_save_products)
        if to_save_gates:
            CheckinList.gates.through.objects.bulk_create(to_save_gates)

    def save_quota_formset(self, log_entries):
        if not self.quota_formset.has_changed():
            return
        qidx = 0
        subevents = list(self.get_queryset().prefetch_related('quotas'))
        to_save_items = []
        to_save_variations = []
        to_delete_quota_ids = []

        if self.sampled_quotas is None:
            if len(self.quota_formset.forms) == 0:
                return
            else:
                for se in subevents:
                    for q in se.quotas.all():
                        to_delete_quota_ids.append(q.pk)
                        log_entries += [
                            q.log_action(action='pretix.event.quota.deleted', user=self.request.user, save=False),
                            se.log_action('pretix.subevent.quota.deleted', user=self.request.user, data={
                                'id': q.pk
                            }, save=False)
                        ]

                if to_delete_quota_ids:
                    Quota.objects.filter(id__in=to_delete_quota_ids).delete()

        for f in self.quota_formset.forms:
            if self.quota_formset._should_delete_form(f) and f in self.quota_formset.extra_forms:
                continue

            selected_items = set(list(self.request.event.items.filter(id__in=[
                i.split('-')[0] for i in f.cleaned_data.get('itemvars', [])
            ])))
            selected_variations = list(ItemVariation.objects.filter(item__event=self.request.event, id__in=[
                i.split('-')[1] for i in f.cleaned_data.get('itemvars', []) if '-' in i
            ]))

            if self.quota_formset._should_delete_form(f):
                for se in subevents:
                    q = list(se.quotas.all())[qidx]
                    log_entries += [
                        q.log_action(action='pretix.event.quota.deleted', user=self.request.user, save=False),
                        se.log_action('pretix.subevent.quota.deleted', user=self.request.user, data={
                            'id': q.pk
                        }, save=False)
                    ]
                    q.delete()
            elif f in self.quota_formset.extra_forms:
                change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
                for se in subevents:
                    q = copy.copy(f.instance)
                    q.pk = None
                    q.subevent = se
                    q.event = self.request.event
                    q.save(clear_cache=False)
                    for _i in selected_items:
                        to_save_items.append(Quota.items.through(quota_id=q.pk, item_id=_i.pk))
                    for _i in selected_variations:
                        to_save_variations.append(Quota.variations.through(quota_id=q.pk, itemvariation_id=_i.pk))

                    change_data['id'] = q.pk
                    log_entries.append(
                        q.log_action(action='pretix.event.quota.added', user=self.request.user,
                                     data=change_data, save=False)
                    )
                    log_entries.append(
                        se.log_action('pretix.subevent.quota.added', user=self.request.user, data=change_data,
                                      save=False)
                    )
            else:
                if f.changed_data:
                    change_data = {k: f.cleaned_data.get(k) for k in f.changed_data}
                    for se in subevents:
                        q = list(se.quotas.all())[qidx]
                        for fname in ('size', 'name', 'release_after_exit', 'ignore_for_event_availability'):
                            setattr(q, fname, f.cleaned_data.get(fname))
                        q.save(clear_cache=False)
                        if 'itemvars' in f.changed_data:
                            q.items.set(selected_items)
                            q.variations.set(selected_variations)
                        log_entries.append(
                            q.log_action(action='pretix.event.quota.added', user=self.request.user,
                                         data=change_data, save=False)
                        )
            qidx += 1
        if to_save_items:
            Quota.items.through.objects.bulk_create(to_save_items)
        if to_save_variations:
            Quota.variations.through.objects.bulk_create(to_save_variations)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['subevents'] = self.get_queryset()
        ctx['filter_form'] = self.filter_form
        ctx['sampled_quotas'] = self.sampled_quotas
        ctx['sampled_lists'] = self.sampled_lists
        ctx['formset'] = self.quota_formset
        ctx['cl_formset'] = self.list_formset
        ctx['itemvar_forms'] = self.itemvar_forms
        ctx['bulk_selected'] = self.request.POST.getlist("_bulk")
        ctx['meta_forms'] = self.meta_forms
        return ctx

    @cached_property
    def sampled_quotas(self):
        all_quotas = Quota.objects.filter(
            subevent__in=self.get_queryset()
        ).annotate(
            item_list=GroupConcat('items__id'),
            var_list=GroupConcat('variations__id'),
        ).values(
            'item_list', 'var_list',
            *(f.name for f in Quota._meta.fields if f.name not in (
                'id', 'event', 'items', 'variations', 'closed',
            ))
        ).order_by('subevent_id', 'id')

        if not all_quotas:
            return Quota.objects.none()

        quotas_by_subevent = defaultdict(set)
        for q in all_quotas:
            if q['item_list']:
                q['item_list'] = ",".join(sorted(q['item_list'].split(',')))
            if q['var_list']:
                q['var_list'] = ",".join(sorted(q['var_list'].split(',')))
            qdata = tuple(q[k] for k in sorted(q.keys()) if k != 'subevent')
            quotas_by_subevent[q['subevent']].add(qdata)

        prev = None
        for se in self.get_queryset():
            if se.pk not in quotas_by_subevent:
                return None

            if prev is None:
                prev = quotas_by_subevent[se.pk]

            if quotas_by_subevent[se.pk] != prev:
                return None
        return se.quotas.all()

    @cached_property
    def sampled_lists(self):
        all_lists = CheckinList.objects.filter(
            subevent__in=self.get_queryset()
        ).annotate(
            item_list=GroupConcat('limit_products__id'),
            gates_list=GroupConcat('gates__id'),
        ).values(
            'item_list', 'gates_list',
            *(f.name for f in CheckinList._meta.fields if f.name not in (
                'id', 'event', 'limit_products', 'gates',
            ))
        ).order_by('subevent_id', 'name', 'pk')

        if not all_lists:
            return SubEvent.objects.none()

        lists_by_subevent = defaultdict(list)
        for cl in all_lists:
            lists_by_subevent[cl.pop('subevent')].append(cl)

        prev = None
        for se in self.get_queryset():
            if se.pk not in lists_by_subevent:
                return None

            if prev is None:
                prev = lists_by_subevent[se.pk]

            if lists_by_subevent[se.pk] != prev:
                return None
        return se.checkinlist_set.all()

    @cached_property
    def is_submitted(self):
        # Usually, django considers a form "bound" / "submitted" on every POST request. However, this view is always
        # called with POST method, even if just to pass the selection of objects to work on, so we want to modify
        # that behaviour
        return '_bulk' in self.request.POST

    def get_form_kwargs(self):
        initial = {}
        mixed_values = set()
        qs = self.get_queryset()

        qs = qs.annotate(
            **{
                # TODO: Once we're on Django 3.2, pass a tzinfo parameter
                # Before Django 3.2, it uses the current timezone, which is hopefully fine
                # as well in all cases we are concerned about
                # See also: https://code.djangoproject.com/ticket/31948
                k + '_day': TruncDate(k)
                for k in ('date_from', 'date_to', 'date_admission', 'presale_start', 'presale_end')
            },
            **{
                k + '_time': TruncTime(k)
                for k in ('date_from', 'date_to', 'date_admission', 'presale_start', 'presale_end')
            },
        )

        fields = {
            'name',
            'location',
            'frontpage_text',
            'geo_lat',
            'geo_lon',
            'is_public',
            'active',
            'date_from_day',
            'date_from_time',
            'date_to_day',
            'date_to_time',
            'date_admission_day',
            'date_admission_time',
            'presale_start_day',
            'presale_start_time',
            'presale_end_day',
            'presale_end_time',
        }
        for k in fields:
            existing_values = list(qs.order_by(k).values(k).annotate(c=Count('*')))
            if len(existing_values) == 1:
                initial[k] = existing_values[0][k]
            elif len(existing_values) > 1:
                mixed_values.add(k)
                initial[k] = None

        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        kwargs['prefix'] = 'bulkedit'
        kwargs['initial'] = initial
        kwargs['queryset'] = self.get_queryset()
        kwargs['mixed_values'] = mixed_values
        if not self.is_submitted:
            kwargs['data'] = None
            kwargs['files'] = None
        return kwargs

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        is_valid = (
            self.is_submitted and
            form.is_valid() and
            self.quota_formset.is_valid() and
            (not self.list_formset or self.list_formset.is_valid()) and
            all(f.is_valid() for f in self.itemvar_forms) and
            all(f.is_valid() for f in self.meta_forms)
        )
        if is_valid:
            return self.form_valid(form)
        else:
            if self.is_submitted:
                messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.form_invalid(form)

    def save_meta(self):
        for f in self.meta_forms:
            if f.prefix + 'value' not in self.request.POST.getlist('_bulk'):
                continue

            if f.cleaned_data.get('value'):
                for obj in self.get_queryset():
                    SubEventMetaValue.objects.update_or_create(
                        property=f.instance.property,
                        subevent=obj,
                        defaults={
                            'value': f.cleaned_data['value']
                        }
                    )
            else:
                SubEventMetaValue.objects.filter(
                    property=f.instance.property,
                    subevent__in=self.get_queryset()
                ).delete()

    def save_itemvars(self):
        for f in self.itemvar_forms:
            u = {}
            if f.prefix + 'price' in self.request.POST.getlist('_bulk'):
                u['price'] = f.cleaned_data.get('price')
            if f.prefix + 'disabled' in self.request.POST.getlist('_bulk'):
                u['disabled'] = f.cleaned_data.get('disabled')
            if f.prefix + 'available_from' in self.request.POST.getlist('_bulk'):
                u['available_from'] = f.cleaned_data.get('available_from')
            if f.prefix + 'available_until' in self.request.POST.getlist('_bulk'):
                u['available_until'] = f.cleaned_data.get('available_until')

            if not u:
                continue

            if isinstance(f, SubEventItemForm):
                if u.get('price') is None and not u.get('disabled') and not u.get('available_from') and not u.get('available_until'):
                    SubEventItem.objects.filter(
                        subevent__in=self.get_queryset(),
                        item=f.instance.item,
                    ).delete()
                else:
                    for obj in self.get_queryset():
                        SubEventItem.objects.update_or_create(
                            subevent=obj,
                            item=f.instance.item,
                            defaults=u
                        )
            elif isinstance(f, SubEventItemVariationForm):
                if u.get('price') is None and not u.get('disabled') and not u.get('available_from') and not u.get('available_until'):
                    SubEventItemVariation.objects.filter(
                        subevent__in=self.get_queryset(),
                        variation=f.instance.variation,
                    ).delete()
                else:
                    for obj in self.get_queryset():
                        SubEventItemVariation.objects.update_or_create(
                            subevent=obj,
                            variation=f.instance.variation,
                            defaults=u
                        )

    @transaction.atomic()
    def form_valid(self, form):
        log_entries = []

        # Main form
        form.save()
        data = {
            k: v for k, v in form.cleaned_data.items() if k in form.changed_data
        }
        data['_raw_bulk_data'] = self.request.POST.dict()
        for obj in self.get_queryset():
            log_entries.append(
                obj.log_action('pretix.subevent.changed', data=data, user=self.request.user, save=False)
            )

        # Formsets
        if '__quotas' in self.request.POST.getlist('_bulk'):
            self.save_quota_formset(log_entries)
        if '__checkinlists' in self.request.POST.getlist('_bulk'):
            self.save_list_formset(log_entries)

        self.save_itemvars()
        self.save_meta()

        if connections['default'].features.can_return_rows_from_bulk_insert:
            LogEntry.objects.bulk_create(log_entries, batch_size=200)
            LogEntry.bulk_postprocess(log_entries)
        else:
            for le in log_entries:
                le.save()
            LogEntry.bulk_postprocess(log_entries)

        self.request.event.cache.clear()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)
