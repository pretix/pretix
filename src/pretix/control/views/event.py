from collections import OrderedDict
from django.shortcuts import render, redirect
from django.utils.functional import cached_property
from django.views.generic.edit import UpdateView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse

from pytz import common_timezones

from pretix.base.forms import VersionedModelForm, SettingsForm
from pretix.base.models import Event
from pretix.base.signals import register_payment_providers
from pretix.control.permissions import EventPermissionRequiredMixin


class EventUpdateForm(VersionedModelForm):
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
    )

    def clean_slug(self):
        return self.instance.slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['readonly'] = 'readonly'

    class Meta:
        model = Event
        localized_fields = '__all__'
        fields = [
            'name',
            'slug',
            'locale',
            'timezone',
            'currency',
            'date_from',
            'date_to',
            'show_date_to',
            'show_times',
            'presale_start',
            'presale_end',
            'payment_term_days',
            'payment_term_last',
        ]


class EventUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Event
    form_class = EventUpdateForm
    template_name = 'pretixcontrol/event/settings.html'
    permission = 'can_change_settings'

    def get_object(self, queryset=None) -> Event:
        return self.request.event

    def get_success_url(self) -> str:
        return reverse('control:event.settings', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        }) + '?success=true'


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
            provider.form = SettingsForm(
                obj=self.request.event,
                data=(self.request.POST if self.request.method == 'POST' else None)
            )
            provider.form.fields = OrderedDict(
                [
                    ('payment_%s__enabled' % provider.identifier,
                     forms.BooleanField(
                         label=_('Enable payment method')
                     )),
                    ('payment_%s__fee_abs' % provider.identifier,
                     forms.DecimalField(
                         label=_('Additional fee'),
                         help_text=_('Absolute value')
                     )),
                    ('payment_%s__fee_percent' % provider.identifier,
                     forms.DecimalField(
                         label=_('Additional fee'),
                         help_text=_('Percentage')
                     )),
                ] + [
                    ('payment_%s_%s' % (provider.identifier, k), v)
                    for k, v in provider.settings_form_fields.items()
                ]
            )
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


def index(request, organizer, event):
    return render(request, 'pretixcontrol/event/index.html', {})
