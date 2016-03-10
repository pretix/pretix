from collections import OrderedDict

from django import forms
from django.contrib import messages
from django.core.files import File
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin

from pretix.base.forms import I18nModelForm
from pretix.base.models import (
    Event, EventPermission, Item, ItemVariation, User,
)
from pretix.base.signals import (
    register_payment_providers, register_ticket_outputs,
)
from pretix.control.forms.event import (
    EventSettingsForm, EventUpdateForm, MailSettingsForm, ProviderForm,
    TicketSettingsForm,
)
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

    @transaction.atomic()
    def form_valid(self, form):
        self.sform.save()
        if self.sform.has_changed():
            self.request.event.log_action('pretix.event.settings', user=self.request.user, data={
                k: self.request.event.settings.get(k) for k in self.sform.changed_data
            })
        if form.has_changed():
            self.request.event.log_action('pretix.event.changed', user=self.request.user, data={
                k: getattr(self.request.event, k) for k in form.changed_data
            })
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
        context['plugins'] = [p for p in get_all_plugins() if not p.name.startswith('.')
                              if getattr(p, 'visible', True)]
        context['plugins_active'] = self.object.get_plugins()
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        plugins_active = self.object.get_plugins()
        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith("plugin:"):
                    module = key.split(":")[1]
                    if value == "enable":
                        self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                                      data={'plugin': module})
                        plugins_active.append(module)
                    else:
                        self.request.event.log_action('pretix.event.plugins.disabled', user=self.request.user,
                                                      data={'plugin': module})
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

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        success = True
        for provider in self.provider_forms:
            if provider.form.is_valid():
                if provider.form.has_changed():
                    self.request.event.log_action(
                        'pretix.event.payment.provider.' + provider.identifier, user=self.request.user, data={
                            k: provider.form.cleaned_data.get(k) for k in provider.form.changed_data
                        }
                    )
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


class MailSettings(EventPermissionRequiredMixin, FormView):
    model = Event
    form_class = MailSettingsForm
    template_name = 'pretixcontrol/event/mail.html'
    permission = 'can_change_settings'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        return context

    def get_success_url(self) -> str:
        return reverse('control:event.settings.mail', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['obj'] = self.request.event
        return kwargs

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.event.log_action(
                    'pretix.event.settings', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )

            if request.POST.get('test', '0').strip() == '1':
                backend = self.request.event.get_mail_backend(force_custom=True)
                try:
                    backend.open()
                except Exception as e:
                    messages.warning(self.request, _('An error occured while contacting the SMTP server: %s') % str(e))
                else:
                    if form.cleaned_data.get('smtp_use_custom'):
                        messages.success(self.request, _('Your changes have been saved and the connection attempt to '
                                                         'your SMTP server was successful. Reme'))
                    else:
                        messages.success(self.request, _('We\'ve been able to contact the SMTP server you configured. '
                                                         'Remember to check the "use custom SMTP server" checkbox, '
                                                         'otherwise your SMTP server will not be used.'))
                finally:
                    backend.close()
            else:
                messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            return self.get(request)


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

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        success = True
        for provider in self.provider_forms:
            if provider.form.is_valid():
                provider.form.save()
                if provider.form.has_changed():
                    self.request.event.log_action(
                        'pretix.event.tickets.provider.' + provider.identifier, user=self.request.user, data={
                            k: (provider.form.cleaned_data.get(k).name
                                if isinstance(provider.form.cleaned_data.get(k), File)
                                else provider.form.cleaned_data.get(k))
                            for k in provider.form.changed_data
                        }
                    )
            else:
                success = False
        form = self.get_form(self.get_form_class())
        if success and form.is_valid():
            form.save()
            if form.has_changed():
                self.request.event.log_action(
                    'pretix.event.tickets.settings', user=self.request.user, data={
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                )
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
                data=(self.request.POST if self.request.method == 'POST' else None),
                files=(self.request.FILES if self.request.method == 'POST' else None)
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


class EventPermissionForm(I18nModelForm):
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
                  queryset=EventPermission.objects.filter(event=self.request.event))

    @cached_property
    def add_form(self):
        return EventPermissionCreateForm(data=self.request.POST if self.request.method == "POST" else None,
                                         prefix="add")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        ctx['add_form'] = self.add_form
        return ctx

    @transaction.atomic()
    def post(self, *args, **kwargs):
        if self.formset.is_valid() and self.add_form.is_valid():
            if self.add_form.has_changed():
                try:
                    self.add_form.instance.user = User.objects.get(email=self.add_form.cleaned_data['user'])
                    self.add_form.instance.user_id = self.add_form.instance.user.id
                    self.add_form.instance.event = self.request.event
                    self.add_form.instance.event_id = self.request.event.id
                except User.DoesNotExist:
                    messages.error(self.request, _('There is no user with the email address you entered.'))
                    return self.get(*args, **kwargs)
                else:
                    if EventPermission.objects.filter(user=self.add_form.instance.user,
                                                      event=self.request.event).exists():
                        messages.error(self.request, _('This user already has permissions for this event.'))
                        return self.get(*args, **kwargs)
                    self.add_form.save()
                    logdata = {
                        k: v for k, v in self.add_form.cleaned_data.items()
                    }
                    logdata['user'] = self.add_form.instance.user_id
                    self.request.event.log_action(
                        'pretix.event.permissions.added', user=self.request.user, data=logdata
                    )
            for form in self.formset.forms:
                if form.has_changed():
                    changedata = {
                        k: form.cleaned_data.get(k) for k in form.changed_data
                    }
                    changedata['user'] = form.instance.user_id
                    self.request.event.log_action(
                        'pretix.event.permissions.changed', user=self.request.user, data=changedata
                    )
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


class EventLive(EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_settings'
    template_name = 'pretixcontrol/event/live.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['issues'] = self.issues
        return ctx

    @cached_property
    def issues(self):
        issues = []
        has_paid_things = (
            Item.objects.filter(event=self.request.event, default_price__gt=0).exists()
            or ItemVariation.objects.filter(item__event=self.request.event, default_price__gt=0).exists()
        )

        has_payment_provider = False
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.is_enabled:
                has_payment_provider = True
                break

        if has_paid_things and not has_payment_provider:
            issues.append(_('You have configured at least one paid product but have not enabled any payment methods.'))

        return issues

    def post(self, request, *args, **kwargs):
        if request.POST.get("live") == "true" and not self.issues:
            request.event.live = True
            request.event.save()
            messages.success(self.request, _('Your shop is live now!'))
        elif request.POST.get("live") == "false":
            request.event.live = False
            request.event.save()
            messages.success(self.request, _('We\'ve taken your shop down. You can re-enable it whenever you want!'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.live', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
