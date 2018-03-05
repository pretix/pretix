import copy

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import F, IntegerField, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.utils.functional import cached_property
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from pretix.base.models.checkin import CheckinList
from pretix.base.models.event import SubEvent, SubEventMetaValue
from pretix.base.models.items import Quota, SubEventItem, SubEventItemVariation
from pretix.control.forms.checkin import CheckinListForm
from pretix.control.forms.filter import SubEventFilterForm
from pretix.control.forms.item import QuotaForm
from pretix.control.forms.subevents import (
    CheckinListFormSet, QuotaFormSet, SubEventForm, SubEventItemForm,
    SubEventItemVariationForm, SubEventMetaValueForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import PaginationMixin
from pretix.control.views.event import MetaDataEditorMixin


class SubEventList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = SubEvent
    context_object_name = 'subevents'
    template_name = 'pretixcontrol/subevents/index.html'
    permission = 'can_change_settings'

    def get_queryset(self):
        sum_tickets_paid = Quota.objects.filter(
            subevent=OuterRef('pk')
        ).order_by().values('subevent').annotate(
            s=Sum('cached_availability_paid_orders')
        ).values(
            's'
        )

        qs = self.request.event.subevents.annotate(
            sum_tickets_paid=Subquery(sum_tickets_paid, output_field=IntegerField())
        ).prefetch_related(
            Prefetch('quotas',
                     queryset=Quota.objects.annotate(s=Coalesce(F('size'), 0)).order_by('-s'),
                     to_attr='first_quotas')
        )
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        for s in ctx['subevents']:
            s.first_quotas = s.first_quotas[:4]
            for q in s.first_quotas:
                q.cached_avail = (
                    (q.cached_availability_state, q.cached_availability_number)
                    if q.cached_availability_time is not None
                    else q.availability(allow_cache=True)
                )
                if q.size is not None:
                    q.percent_paid = min(
                        100,
                        round(q.cached_availability_paid_orders / q.size * 100) if q.size > 0 else 100
                    )
        return ctx

    @cached_property
    def filter_form(self):
        return SubEventFilterForm(data=self.request.GET)


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
        if self.get_object().orderposition_set.count() > 0:
            messages.error(request, pgettext_lazy('subevent', 'A date can not be deleted if orders already have been '
                                                  'placed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if self.object.orderposition_set.count() > 0:
            messages.error(request, pgettext_lazy('subevent', 'A date can not be deleted if orders already have been '
                                                  'placed.'))
            return HttpResponseRedirect(self.get_success_url())
        elif not self.object.allow_delete():  # checking if this is the last date in the event series
            messages.error(request, pgettext_lazy('subevent', 'The last date of an event series can not be deleted.'))
            return HttpResponseRedirect(self.get_success_url())
        else:
            self.object.log_action('pretix.subevent.deleted', user=self.request.user)
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

    def _make_meta_form(self, p, val_instances):
        if not hasattr(self, '_default_meta'):
            self._default_meta = self.request.event.meta_data

        return self.meta_form(
            prefix='prop-{}'.format(p.pk),
            property=p,
            default=self._default_meta.get(p.name, ''),
            instance=val_instances.get(p.pk, self.meta_model(property=p, subevent=self.object)),
            data=(self.request.POST if self.request.method == "POST" else None)
        )

    @cached_property
    def cl_formset(self):
        extra = 0
        kwargs = {}

        if self.copy_from:
            kwargs['initial'] = [
                {
                    'name': cl.name,
                    'all_products': cl.all_products,
                    'limit_products': cl.limit_products.all(),
                    'include_pending': cl.include_pending,
                } for cl in self.copy_from.checkinlist_set.prefetch_related('limit_products')
            ]
            extra = len(kwargs['initial'])
        elif not self.object:
            kwargs['initial'] = [
                {
                    'name': '',
                    'all_products': True,
                    'include_pending': False,
                }
            ]
            extra = 1

        formsetclass = inlineformset_factory(
            SubEvent, CheckinList,
            form=CheckinListForm, formset=CheckinListFormSet,
            can_order=False, can_delete=True, extra=extra,
        )
        if self.object:
            kwargs['queryset'] = self.object.checkinlist_set.prefetch_related('limit_products')

        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            instance=self.object,
                            event=self.request.event, **kwargs)

    @cached_property
    def formset(self):
        extra = 0
        kwargs = {}

        if self.copy_from:
            kwargs['initial'] = [
                {
                    'size': q.size,
                    'name': q.name,
                    'itemvars': [str(i.pk) for i in q.items.all()] + [
                        '{}-{}'.format(v.item_id, v.pk) for v in q.variations.all()
                    ]
                } for q in self.copy_from.quotas.prefetch_related('items', 'variations')
            ]
            extra = len(kwargs['initial'])

        formsetclass = inlineformset_factory(
            SubEvent, Quota,
            form=QuotaForm, formset=QuotaFormSet,
            can_order=False, can_delete=True, extra=extra,
        )
        if self.object:
            kwargs['queryset'] = self.object.quotas.prefetch_related('items', 'variations')

        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            instance=self.object,
                            event=self.request.event, **kwargs)

    def save_cl_formset(self, obj):
        for form in self.cl_formset.initial_forms:
            if form in self.cl_formset.deleted_forms:
                if not form.instance.pk:
                    continue
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
        return ctx

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object'):
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
                sei.item_id: SubEventItem(item=sei.item, price=sei.price)
                for sei in SubEventItem.objects.filter(subevent=self.copy_from).select_related('item')
            }
            se_var_instances = {
                sei.variation_id: SubEventItemVariation(variation=sei.variation, price=sei.price)
                for sei in SubEventItemVariation.objects.filter(subevent=self.copy_from).select_related('variation')
            }

        formlist = []
        for i in self.request.event.items.filter(active=True).prefetch_related('variations'):
            if i.has_variations:
                for v in i.variations.all():
                    inst = se_var_instances.get(v.pk) or SubEventItemVariation(subevent=self.object, variation=v)
                    formlist.append(SubEventItemVariationForm(
                        prefix='itemvar-{}'.format(v.pk),
                        item=i, variation=v,
                        instance=inst,
                        data=(self.request.POST if self.request.method == "POST" else None)
                    ))
            else:
                inst = se_item_instances.get(i.pk) or SubEventItem(subevent=self.object, item=i)
                formlist.append(SubEventItemForm(
                    prefix='item-{}'.format(i.pk),
                    item=i,
                    instance=inst,
                    data=(self.request.POST if self.request.method == "POST" else None)
                ))
        return formlist

    def is_valid(self, form):
        return form.is_valid() and all([f.is_valid() for f in self.itemvar_forms]) and self.formset.is_valid() and (
            all([f.is_valid() for f in self.meta_forms])
        ) and self.cl_formset.is_valid()


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
            return self.form_valid(form)
        else:
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
        if form.has_changed():
            self.object.log_action(
                'pretix.subevent.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

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

    def post(self, request, *args, **kwargs):
        self.object = SubEvent(event=self.request.event)
        form = self.get_form()
        if self.is_valid(form):
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        if self.copy_from:
            i = copy.copy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
        else:
            kwargs['instance'] = SubEvent(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, pgettext_lazy('subevent', 'The new date has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.subevent.added', data=dict(form.cleaned_data), user=self.request.user)

        self.save_formset(form.instance)
        self.save_cl_formset(form.instance)
        for f in self.itemvar_forms:
            f.instance.subevent = form.instance
            f.save()
        self.object = form.instance
        self.save_meta()
        return ret
