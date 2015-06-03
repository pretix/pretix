from collections import OrderedDict

from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils.functional import cached_property
from django.views.generic import FormView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
from pretix.control.forms.event import ProviderForm, TicketSettingsForm, EventSettingsForm, EventUpdateForm
from pretix.base.models import Event
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
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.settings.plugins', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        }) + '?success=true'


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
            return redirect(self.get_success_url())
        else:
            return self.get(request)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.payment', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        }) + '?success=true'


class TicketSettings(EventPermissionRequiredMixin, FormView):
    model = Event
    form_class = TicketSettingsForm
    template_name = 'pretixcontrol/event/tickets.html'
    permission = 'can_change_settings'

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['providers'] = self.provider_forms
        return context

    def get_success_url(self) -> str:
        return reverse('control:event.settings.tickets', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        }) + '?success=true'

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
    return render(request, 'pretixcontrol/event/index.html', {})
