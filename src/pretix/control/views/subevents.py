from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from pretix.base.models.event import SubEvent
from pretix.base.models.items import Quota, SubEventItem, SubEventItemVariation
from pretix.control.forms.item import QuotaForm
from pretix.control.forms.subevents import (
    QuotaFormSet, SubEventForm, SubEventItemForm, SubEventItemVariationForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin


class SubEventList(EventPermissionRequiredMixin, ListView):
    model = SubEvent
    context_object_name = 'subevents'
    paginate_by = 30
    template_name = 'pretixcontrol/subevents/index.html'
    permission = 'can_change_settings'

    def get_queryset(self):
        qs = self.request.event.subevents.all()
        return qs


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
            raise Http404(_("The requested sub-event does not exist."))

    def get(self, request, *args, **kwargs):
        if self.get_object().orderposition_set.count() > 0:
            messages.error(request, _('A sub-event can not be deleted if orders already have been placed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if self.get_object().orderposition_set.count() > 0:
            messages.error(request, _('A sub-event can not be deleted if orders already have been placed.'))
            return HttpResponseRedirect(self.get_success_url())
        else:
            self.object.log_action('pretix.subevent.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected subevent has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.subevents', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class SubEventEditorMixin:
    @cached_property
    def formset(self):
        formsetclass = inlineformset_factory(
            SubEvent, Quota,
            form=QuotaForm, formset=QuotaFormSet,
            can_order=False, can_delete=True, extra=0
        )
        return formsetclass(self.request.POST if self.request.method == "POST" else None,
                            instance=self.object,
                            event=self.request.event)

    def save_formset(self, obj):
        for form in self.formset.initial_forms:
            if form in self.formset.deleted_forms:
                if not form.instance.pk:
                    continue
                obj.log_action(
                    'pretix.subevent.quota.deleted', user=self.request.user, data={
                        'id': form.instance.pk
                    }
                )
                form.instance.delete()
                form.instance.pk = None
            elif form.has_changed():
                form.instance.question = obj
                form.save()
                change_data = {k: form.cleaned_data.get(k) for k in form.changed_data}
                change_data['id'] = form.instance.pk
                obj.log_action(
                    'pretix.subevent.quota.changed',
                    user=self.request.user, data=change_data
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
            obj.log_action(
                'pretix.subevent.quota.added',
                user=self.request.user, data=change_data
            )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        ctx['itemvar_forms'] = self.itemvar_forms
        return ctx

    @cached_property
    def itemvar_forms(self):
        se_item_instances = {
            sei.item_id: sei for sei in SubEventItem.objects.filter(subevent=self.object)
        }
        se_var_instances = {
            sei.variation_id: sei for sei in SubEventItemVariation.objects.filter(subevent=self.object)
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
        return form.is_valid() and all([f.is_valid() for f in self.itemvar_forms]) and self.formset.is_valid()


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
            raise Http404(_("The requested sub-event does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        self.save_formset(self.object)

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
        kwargs['instance'] = getattr(self, 'object', SubEvent(event=self.request.event))
        kwargs['event'] = self.request.event
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new sub-event has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.subevent.added', data=dict(form.cleaned_data), user=self.request.user)

        self.save_formset(form.instance)
        for f in self.itemvar_forms:
            f.instance.subevent = form.instance
            f.save()

        return ret
