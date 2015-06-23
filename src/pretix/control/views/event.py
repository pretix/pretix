from collections import OrderedDict
from django import forms

from django.contrib import messages
from django.db.models import Sum
from django.forms import inlineformset_factory, formset_factory, modelformset_factory, BaseInlineFormSet
from django.shortcuts import render, redirect
from django.utils.functional import cached_property
from django.views.generic import FormView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
from pretix.base.forms import VersionedModelForm
from pretix.control.forms.event import ProviderForm, TicketSettingsForm, EventSettingsForm, EventUpdateForm
from pretix.base.models import Event, OrderPosition, Order, Item, EventPermission, User
from pretix.base.signals import register_payment_providers, register_ticket_outputs
from pretix.control.permissions import EventPermissionRequiredMixin
from . import UpdateView


class EventUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Event
    form_class = EventUpdateForm
    template_name = 'pretixcontrol/event/settings.html'
    permission = 'can_change_settings'

    @cached_property
    def object(self) -> Event:
        return self.request.event

    def get_object(self, queryset=None) -> Event:
        return self.object

    @cached_property
    def sform(self):
        return EventSettingsForm(
            obj=self.object,
            prefix='settings',
            data=self.request.POST if self.request.method == 'POST' else None
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['sform'] = self.sform
        return context

    def form_valid(self, form):
        self.sform.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.settings', kwargs={
            'organizer': self.object.organizer.slug,
            'event': self.object.slug,
        })

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid() and self.sform.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class EventPlugins(EventPermissionRequiredMixin, TemplateView, SingleObjectMixin):
    model = Event
    context_object_name = 'event'
    permission = 'can_change_settings'
    template_name = 'pretixcontrol/event/plugins.html'

    def get_object(self, queryset=None) -> Event:
        return self.request.event

    def get_context_data(self, *args, **kwargs) -> dict:
        from pretix.base.plugins import get_all_plugins

        context = super().get_context_data(*args, **kwargs)
        context['plugins'] = [p for p in get_all_plugins() if not p.name.startswith('.')]
        context['plugins_active'] = self.object.get_plugins()
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        plugins_active = self.object.get_plugins()
        for key, value in request.POST.items():
            if key.startswith("plugin:"):
                module = key.split(":")[1]
                if value == "enable":
                    plugins_active.append(module)
                else:
                    plugins_active.remove(module)
        self.object.plugins = ",".join(plugins_active)
        self.object.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.settings.plugins', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        })


class PaymentSettings(EventPermissionRequiredMixin, TemplateView, SingleObjectMixin):
    model = Event
    context_object_name = 'event'
    permission = 'can_change_settings'
    template_name = 'pretixcontrol/event/payment.html'

    def get_object(self, queryset=None) -> Event:
        return self.request.event

    @cached_property
    def provider_forms(self) -> list:
        providers = []
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            provider.form = ProviderForm(
                obj=self.request.event,
                settingspref='payment_%s_' % provider.identifier,
                data=(self.request.POST if self.request.method == 'POST' else None)
            )
            provider.form.fields = OrderedDict(
                [
                    ('payment_%s_%s' % (provider.identifier, k), v)
                    for k, v in provider.settings_form_fields.items()
                ]
            )
            provider.settings_content = provider.settings_content_render(self.request)
            provider.form.prepare_fields()
            if provider.settings_content or provider.form.fields:
                # Exclude providers which do not provide any settings
                providers.append(provider)
        return providers

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        context['providers'] = self.provider_forms
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        success = True
        for provider in self.provider_forms:
            if provider.form.is_valid():
                provider.form.save()
            else:
                success = False
        if success:
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            return self.get(request)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.payment', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        })


class TicketSettings(EventPermissionRequiredMixin, FormView):
    model = Event
    form_class = TicketSettingsForm
    template_name = 'pretixcontrol/event/tickets.html'
    permission = 'can_change_settings'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['providers'] = self.provider_forms
        return context

    def get_success_url(self) -> str:
        return reverse('control:event.settings.tickets', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['obj'] = self.request.event
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.prepare_fields()
        return form

    def post(self, request, *args, **kwargs):
        success = True
        for provider in self.provider_forms:
            if provider.form.is_valid():
                provider.form.save()
            else:
                success = False
        form = self.get_form(self.get_form_class())
        if success and form.is_valid():
            form.save()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            return self.get(request)

    @cached_property
    def provider_forms(self) -> list:
        providers = []
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            provider.form = ProviderForm(
                obj=self.request.event,
                settingspref='ticketoutput_%s_' % provider.identifier,
                data=(self.request.POST if self.request.method == 'POST' else None)
            )
            provider.form.fields = OrderedDict(
                [
                    ('ticketoutput_%s_%s' % (provider.identifier, k), v)
                    for k, v in provider.settings_form_fields.items()
                ]
            )
            provider.settings_content = provider.settings_content_render(self.request)
            provider.form.prepare_fields()
            providers.append(provider)
        return providers


def index(request, organizer, event):
    ctx = {
        'products_active': Item.objects.current.filter(
            event=request.event,
            active=True,
        ).count(),
        'tickets_total': OrderPosition.objects.current.filter(
            order__event=request.event,
            item__admission=True
        ).count(),
        'tickets_revenue': Order.objects.current.filter(
            event=request.event,
            status=Order.STATUS_PAID,
        ).aggregate(sum=Sum('total'))['sum'],
        'tickets_sold': OrderPosition.objects.current.filter(
            order__event=request.event,
            order__status=Order.STATUS_PAID,
            item__admission=True
        ).count()
    }
    return render(request, 'pretixcontrol/event/index.html', ctx)


class EventPermissionForm(VersionedModelForm):
    class Meta:
        model = EventPermission
        fields = (
            'can_change_settings', 'can_change_items', 'can_change_permissions', 'can_view_orders',
            'can_change_orders'
        )


class EventPermissionCreateForm(EventPermissionForm):
    user = forms.EmailField(required=False, label=_('User'))


class EventPermissions(EventPermissionRequiredMixin, TemplateView):
    model = Event
    form_class = TicketSettingsForm
    template_name = 'pretixcontrol/event/permissions.html'
    permission = 'can_change_permissions'

    @cached_property
    def formset(self):
        fs = modelformset_factory(
            EventPermission,
            form=EventPermissionForm,
            can_delete=True, can_order=False, extra=0
        )
        return fs(data=self.request.POST if self.request.method == "POST" else None,
                  prefix="formset",
                  queryset=EventPermission.objects.current.filter(event=self.request.event))

    @cached_property
    def add_form(self):
        return EventPermissionCreateForm(data=self.request.POST if self.request.method == "POST" else None,
                                         prefix="add")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        ctx['add_form'] = self.add_form
        return ctx

    def post(self, *args, **kwargs):
        if self.formset.is_valid() and self.add_form.is_valid():
            if self.add_form.has_changed():
                try:
                    self.add_form.instance.user = User.objects.get(identifier=self.add_form.cleaned_data['user'])
                    self.add_form.instance.user_id = self.add_form.instance.user.id
                    self.add_form.instance.event = self.request.event
                    self.add_form.instance.event_id = self.request.event.identity
                except User.DoesNotExist:
                    messages.error(self.request, _('There is no user with the email address you entered.'))
                    return self.get(*args, **kwargs)
                else:
                    if EventPermission.objects.current.filter(user=self.add_form.instance.user,
                                                              event=self.request.event).exists():
                        messages.error(self.request, _('This user already has permissions for this event.'))
                        return self.get(*args, **kwargs)
                    self.add_form.save()
            for form in self.formset.forms:
                if form.instance.user_id == self.request.user.pk:
                    if not form.cleaned_data['can_change_permissions'] or form in self.formset.deleted_forms:
                        messages.error(self.request, _('You cannot remove your own permission to view this page.'))
                        return self.get(*args, **kwargs)

            self.formset.save()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('Your changes could not be saved.'))
            return self.get(*args, **kwargs)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.permissions', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
