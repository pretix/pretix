from collections import OrderedDict

from django import forms
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms import modelformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView, ListView
from django.views.generic.base import TemplateView, View
from django.views.generic.detail import SingleObjectMixin

from pretix.base.forms import I18nModelForm
from pretix.base.models import (
    CachedTicket, Event, EventPermission, Item, ItemVariation, LogEntry, Order,
    RequiredAction, User, Voucher,
)
from pretix.base.services import tickets
from pretix.base.services.invoices import build_preview_invoice_pdf
from pretix.base.services.mail import SendMailException, mail
from pretix.base.signals import (
    event_live_issues, register_payment_providers, register_ticket_outputs,
)
from pretix.control.forms.event import (
    DisplaySettingsForm, EventSettingsForm, EventUpdateForm,
    InvoiceSettingsForm, MailSettingsForm, PaymentSettingsForm, ProviderForm,
    TicketSettingsForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri
from pretix.presale.style import regenerate_css

from . import UpdateView
from ..logdisplay import OVERVIEW_BLACKLIST


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

    @transaction.atomic
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
                              and getattr(p, 'visible', True)]
        context['plugins_active'] = self.object.get_plugins()
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        from pretix.base.plugins import get_all_plugins

        self.object = self.get_object()

        plugins_active = self.object.get_plugins()
        plugins_available = {
            p.module: p for p in get_all_plugins()
            if not p.name.startswith('.') and getattr(p, 'visible', True)
        }

        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith("plugin:"):
                    module = key.split(":")[1]
                    if value == "enable" and module in plugins_available:
                        if getattr(plugins_available[module], 'restricted', False):
                            if not request.user.is_superuser:
                                continue
                        self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                                      data={'plugin': module})
                        if module not in plugins_active:
                            plugins_active.append(module)
                    else:
                        self.request.event.log_action('pretix.event.plugins.disabled', user=self.request.user,
                                                      data={'plugin': module})
                        if module in plugins_active:
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
        context['sform'] = self.sform
        return context

    @cached_property
    def sform(self):
        return PaymentSettingsForm(
            obj=self.object,
            prefix='settings',
            data=self.request.POST if self.request.method == 'POST' else None
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        context['providers'] = self.provider_forms
        return self.render_to_response(context)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        success = self.sform.is_valid()
        if success:
            self.sform.save()
            if self.sform.has_changed():
                self.request.event.log_action('pretix.event.settings', user=self.request.user, data={
                    k: self.request.event.settings.get(k) for k in self.sform.changed_data
                })
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
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.payment', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        })


class EventSettingsFormView(EventPermissionRequiredMixin, FormView):
    model = Event
    permission = 'can_change_settings'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['obj'] = self.request.event
        return kwargs

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.event.log_action(
                    'pretix.event.settings', user=self.request.user, data={
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


class InvoiceSettings(EventSettingsFormView):
    model = Event
    form_class = InvoiceSettingsForm
    template_name = 'pretixcontrol/event/invoicing.html'
    permission = 'can_change_settings'

    def get_success_url(self) -> str:
        if 'preview' in self.request.POST:
            return reverse('control:event.settings.invoice.preview', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug
            })
        return reverse('control:event.settings.invoice', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })


class InvoicePreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_settings'

    def get(self, request, *args, **kwargs):
        pdf = build_preview_invoice_pdf(request.event)
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="invoice-preview.pdf"'
        return resp


class DisplaySettings(EventSettingsFormView):
    model = Event
    form_class = DisplaySettingsForm
    template_name = 'pretixcontrol/event/display.html'
    permission = 'can_change_settings'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.display', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            if form.has_changed():
                self.request.event.log_action(
                    'pretix.event.settings', user=self.request.user, data={
                        k: (form.cleaned_data.get(k).name
                            if isinstance(form.cleaned_data.get(k), File)
                            else form.cleaned_data.get(k))
                        for k in form.changed_data
                    }
                )
            regenerate_css.apply_async(args=(self.request.event.pk,))
            messages.success(self.request, _('Your changes have been saved. Please note that it can '
                                             'take a short period of time until your changes become '
                                             'active.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)


class MailSettings(EventSettingsFormView):
    model = Event
    form_class = MailSettingsForm
    template_name = 'pretixcontrol/event/mail.html'
    permission = 'can_change_settings'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.mail', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    @transaction.atomic
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
                    backend.test(self.request.event.settings.mail_from)
                except Exception as e:
                    messages.warning(self.request, _('An error occured while contacting the SMTP server: %s') % str(e))
                else:
                    if form.cleaned_data.get('smtp_use_custom'):
                        messages.success(self.request, _('Your changes have been saved and the connection attempt to '
                                                         'your SMTP server was successful.'))
                    else:
                        messages.success(self.request, _('We\'ve been able to contact the SMTP server you configured. '
                                                         'Remember to check the "use custom SMTP server" checkbox, '
                                                         'otherwise your SMTP server will not be used.'))
            else:
                messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)


class TicketSettingsPreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_settings'

    @cached_property
    def output(self):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.kwargs.get('output'):
                return provider

    def get(self, request, *args, **kwargs):
        if not self.output:
            messages.error(request, _('You requested an invalid ticket output type.'))
            return redirect(self.get_error_url())

        fname, mimet, data = tickets.preview(self.request.event.pk, self.output.identifier)
        resp = HttpResponse(data, content_type=mimet)
        ftype = fname.split(".")[-1]
        resp['Content-Disposition'] = 'attachment; filename="ticket-preview.{}"'.format(ftype)
        return resp

    def get_error_url(self) -> str:
        return reverse('control:event.settings.tickets', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
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

    @transaction.atomic
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
                    CachedTicket.objects.filter(
                        order_position__order__event=self.request.event, provider=provider.identifier
                    ).delete()
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

            provider.preview_allowed = True
            for k, v in provider.settings_form_fields.items():
                if v.required and not self.request.event.settings.get('ticketoutput_%s_%s' % (provider.identifier, k)):
                    provider.preview_allowed = False
                    break

            providers.append(provider)
        return providers


class EventPermissionForm(I18nModelForm):
    class Meta:
        model = EventPermission
        fields = (
            'can_change_settings', 'can_change_items', 'can_change_permissions', 'can_view_orders',
            'can_change_orders', 'can_view_vouchers', 'can_change_vouchers'
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

    def _send_invite(self, instance):
        try:
            mail(
                instance.invite_email,
                _('Account information changed'),
                'pretixcontrol/email/invitation.txt',
                {
                    'user': self,
                    'event': self.request.event.name,
                    'url': build_absolute_uri('control:auth.invite', kwargs={
                        'token': instance.invite_token
                    })
                },
                event=None,
                locale=self.request.LANGUAGE_CODE
            )
        except SendMailException:
            pass  # Already logged

    @transaction.atomic
    def post(self, *args, **kwargs):
        if self.formset.is_valid() and self.add_form.is_valid():
            if self.add_form.has_changed():
                logdata = {
                    k: v for k, v in self.add_form.cleaned_data.items()
                }

                try:
                    self.add_form.instance.event = self.request.event
                    self.add_form.instance.event_id = self.request.event.id
                    self.add_form.instance.user = User.objects.get(email=self.add_form.cleaned_data['user'])
                    self.add_form.instance.user_id = self.add_form.instance.user.id
                except User.DoesNotExist:
                    self.add_form.instance.invite_email = self.add_form.cleaned_data['user']
                    if EventPermission.objects.filter(invite_email=self.add_form.instance.invite_email,
                                                      event=self.request.event).exists():
                        messages.error(self.request, _('This user already has been invited for this event.'))
                        return self.get(*args, **kwargs)

                    self.add_form.save()
                    self._send_invite(self.add_form.instance)

                    self.request.event.log_action(
                        'pretix.event.permissions.invited', user=self.request.user, data=logdata
                    )
                else:
                    if EventPermission.objects.filter(user=self.add_form.instance.user,
                                                      event=self.request.event).exists():
                        messages.error(self.request, _('This user already has permissions for this event.'))
                        return self.get(*args, **kwargs)
                    self.add_form.save()
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

            for form in self.formset.deleted_forms:
                logdata = {
                    k: v for k, v in form.cleaned_data.items()
                }
                self.request.event.log_action(
                    'pretix.event.permissions.deleted', user=self.request.user, data=logdata
                )

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
            if provider.is_enabled and provider.identifier != 'free':
                has_payment_provider = True
                break

        if has_paid_things and not has_payment_provider:
            issues.append(_('You have configured at least one paid product but have not enabled any payment methods.'))

        if not self.request.event.quotas.exists():
            issues.append(_('You need to configure at least one quota to sell anything.'))

        responses = event_live_issues.send(self.request.event)
        for receiver, response in responses:
            if response:
                issues.append(response)

        return issues

    def post(self, request, *args, **kwargs):
        if request.POST.get("live") == "true" and not self.issues:
            request.event.live = True
            request.event.save()
            self.request.event.log_action(
                'pretix.event.live.activated', user=self.request.user, data={}
            )
            messages.success(self.request, _('Your shop is live now!'))
        elif request.POST.get("live") == "false":
            request.event.live = False
            request.event.save()
            self.request.event.log_action(
                'pretix.event.live.deactivated', user=self.request.user, data={}
            )
            messages.success(self.request, _('We\'ve taken your shop down. You can re-enable it whenever you want!'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.live', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })


class EventLog(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixcontrol/event/logs.html'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        qs = self.request.event.logentry_set.all().select_related('user', 'content_type').order_by('-datetime')
        qs = qs.exclude(action_type__in=OVERVIEW_BLACKLIST)
        if not self.request.eventperm.can_view_orders:
            qs = qs.exclude(content_type=ContentType.objects.get_for_model(Order))
        if not self.request.eventperm.can_view_vouchers:
            qs = qs.exclude(content_type=ContentType.objects.get_for_model(Voucher))

        if self.request.GET.get('user') == 'yes':
            qs = qs.filter(user__isnull=False)
        elif self.request.GET.get('user') == 'no':
            qs = qs.filter(user__isnull=True)
        elif self.request.GET.get('user'):
            qs = qs.filter(user_id=self.request.GET.get('user'))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['userlist'] = self.request.event.user_perms.select_related('user')
        return ctx


class EventActions(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixcontrol/event/actions.html'
    model = RequiredAction
    context_object_name = 'actions'
    paginate_by = 20
    permission = 'can_change_orders'

    def get_queryset(self):
        qs = self.request.event.requiredaction_set.filter(done=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        for a in ctx['actions']:
            a.display = a.display(self.request)
        return ctx


class EventActionDiscard(EventPermissionRequiredMixin, View):
    permission = 'can_change_orders'

    def get(self, request, **kwargs):
        action = get_object_or_404(RequiredAction, event=request.event, pk=kwargs.get('id'))
        action.done = True
        action.user = request.user
        action.save()
        messages.success(self.request, _('The issue has been marked as resolved!'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })
