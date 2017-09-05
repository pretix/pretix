import re
from collections import OrderedDict
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.utils import translation
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext, ugettext_lazy as _
from django.views.generic import DeleteView, FormView, ListView
from django.views.generic.base import TemplateView, View
from django.views.generic.detail import SingleObjectMixin
from i18nfield.strings import LazyI18nString
from pytz import timezone

from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, Item, ItemVariation, LogEntry,
    Order, OrderPosition, RequiredAction, TaxRule, Voucher,
)
from pretix.base.models.event import EventMetaValue
from pretix.base.models.orders import OrderFee
from pretix.base.services import tickets
from pretix.base.services.invoices import build_preview_invoice_pdf
from pretix.base.signals import event_live_issues, register_ticket_outputs
from pretix.control.forms.event import (
    CommentForm, DisplaySettingsForm, EventMetaValueForm, EventSettingsForm,
    EventUpdateForm, InvoiceSettingsForm, MailSettingsForm,
    PaymentSettingsForm, ProviderForm, TaxRuleForm, TicketSettingsForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.urls import build_absolute_uri
from pretix.presale.style import regenerate_css

from . import CreateView, UpdateView
from ..logdisplay import OVERVIEW_BLACKLIST


class MetaDataEditorMixin:
    meta_form = EventMetaValueForm
    meta_model = EventMetaValue

    @cached_property
    def meta_forms(self):
        if hasattr(self, 'object') and self.object:
            val_instances = {
                v.property_id: v for v in self.object.meta_values.all()
            }
        else:
            val_instances = {}

        formlist = []

        for p in self.request.organizer.meta_properties.all():
            formlist.append(self._make_meta_form(p, val_instances))
        return formlist

    def _make_meta_form(self, p, val_instances):
        return self.meta_form(
            prefix='prop-{}'.format(p.pk),
            property=p,
            instance=val_instances.get(p.pk, self.meta_model(property=p, event=self.object)),
            data=(self.request.POST if self.request.method == "POST" else None)
        )

    def save_meta(self):
        for f in self.meta_forms:
            if f.cleaned_data.get('value'):
                f.save()
            elif f.instance and f.instance.pk:
                f.delete()


class EventUpdate(EventPermissionRequiredMixin, MetaDataEditorMixin, UpdateView):
    model = Event
    form_class = EventUpdateForm
    template_name = 'pretixcontrol/event/settings.html'
    permission = 'can_change_event_settings'

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
        context['meta_forms'] = self.meta_forms
        return context

    @transaction.atomic
    def form_valid(self, form):
        self.sform.save()
        self.save_meta()

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
        if form.is_valid() and self.sform.is_valid() and all([f.is_valid() for f in self.meta_forms]):
            # reset timezone
            zone = timezone(self.sform.cleaned_data['timezone'])
            event = form.instance
            event.date_from = self.reset_timezone(zone, event.date_from)
            event.date_to = self.reset_timezone(zone, event.date_to)
            event.presale_start = self.reset_timezone(zone, event.presale_start)
            event.presale_end = self.reset_timezone(zone, event.presale_end)
            return self.form_valid(form)
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.form_invalid(form)

    @staticmethod
    def reset_timezone(tz, dt):
        return tz.localize(dt.replace(tzinfo=None)) if dt is not None else None


class EventPlugins(EventPermissionRequiredMixin, TemplateView, SingleObjectMixin):
    model = Event
    context_object_name = 'event'
    permission = 'can_change_event_settings'
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
    permission = 'can_change_event_settings'
    template_name = 'pretixcontrol/event/payment.html'

    def get_object(self, queryset=None) -> Event:
        return self.request.event

    @cached_property
    def provider_forms(self) -> list:
        providers = []
        for provider in self.request.event.get_payment_providers().values():
            provider.form = ProviderForm(
                obj=self.request.event,
                settingspref=provider.settings.get_prefix(),
                data=(self.request.POST if self.request.method == 'POST' else None)
            )
            provider.form.fields = OrderedDict(
                [
                    ('%s%s' % (provider.settings.get_prefix(), k), v)
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
    permission = 'can_change_event_settings'

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
    permission = 'can_change_event_settings'

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
    permission = 'can_change_event_settings'

    def get(self, request, *args, **kwargs):
        fname, ftype, fcontent = build_preview_invoice_pdf(request.event)
        resp = HttpResponse(fcontent, content_type=ftype)
        resp['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)
        return resp


class DisplaySettings(EventSettingsFormView):
    model = Event
    form_class = DisplaySettingsForm
    template_name = 'pretixcontrol/event/display.html'
    permission = 'can_change_event_settings'

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
    permission = 'can_change_event_settings'

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


class MailSettingsPreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_event_settings'

    # return the origin text if key is missing in dict
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'

    @staticmethod
    def generate_order_fullname(slug, code):
        return '{event}-{code}'.format(event=slug.upper(), code=code)

    # create data which depend on locale
    def localized_data(self):
        return {
            'date': date_format(now() + timedelta(days=7), 'SHORT_DATE_FORMAT'),
            'expire_date': date_format(now() + timedelta(days=15), 'SHORT_DATE_FORMAT'),
            'payment_info': _('{} {} has been transferred to account <9999-9999-9999-9999> at {}').format(
                42.23, self.request.event.currency, date_format(now(), 'SHORT_DATETIME_FORMAT'))
        }

    # create index-language mapping
    @cached_property
    def supported_locale(self):
        locales = {}
        for idx, val in enumerate(settings.LANGUAGES):
            if val[0] in self.request.event.settings.locales:
                locales[str(idx)] = val[0]
        return locales

    @cached_property
    def items(self):
        return {
            'mail_text_order_placed': ['total', 'currency', 'date', 'invoice_company',
                                       'event', 'payment_info', 'url', 'invoice_name'],
            'mail_text_order_paid': ['event', 'url', 'invoice_name', 'invoice_company', 'payment_info'],
            'mail_text_order_free': ['event', 'url', 'invoice_name', 'invoice_company'],
            'mail_text_resend_link': ['event', 'url', 'invoice_name', 'invoice_company'],
            'mail_text_resend_all_links': ['event', 'orders'],
            'mail_text_order_changed': ['event', 'url', 'invoice_name', 'invoice_company'],
            'mail_text_order_expire_warning': ['event', 'url', 'expire_date', 'invoice_name', 'invoice_company'],
            'mail_text_waiting_list': ['event', 'url', 'product', 'hours', 'code'],
            'mail_text_order_canceled': ['code', 'event', 'url'],
            'mail_text_order_custom_mail': ['expire_date', 'event', 'code', 'date', 'url',
                                            'invoice_name', 'invoice_company']
        }

    @cached_property
    def base_data(self):
        user_orders = [
            {'code': 'F8VVL', 'secret': '6zzjnumtsx136ddy'},
            {'code': 'HIDHK', 'secret': '98kusd8ofsj8dnkd'},
            {'code': 'OPKSB', 'secret': '09pjdksflosk3njd'}
        ]
        orders = [' - {} - {}'.format(self.generate_order_fullname(self.request.event.slug, order['code']),
                                      self.generate_order_url(order['code'], order['secret']))
                  for order in user_orders]
        return {
            'event': self.request.event.name,
            'total': 42.23,
            'currency': self.request.event.currency,
            'url': self.generate_order_url(user_orders[0]['code'], user_orders[0]['secret']),
            'orders': '\n'.join(orders),
            'hours': self.request.event.settings.waiting_list_hours,
            'product': _('Sample Admission Ticket'),
            'code': '68CYU2H6ZTP3WLK5',
            'invoice_name': _('John Doe'),
            'invoice_company': _('Sample Corporation'),
            'payment_info': _('Please transfer money to this bank account: 9999-9999-9999-9999')
        }

    def generate_order_url(self, code, secret):
        return build_absolute_uri('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': code,
            'secret': secret
        })

    # get all supported placeholders with dummy values
    def placeholders(self, item):
        supported = {}
        local_data = self.localized_data()
        for key in self.items.get(item):
            supported[key] = self.base_data.get(key) if key in self.base_data else local_data.get(key)
        return self.SafeDict(supported)

    def post(self, request, *args, **kwargs):
        preview_item = request.POST.get('item', '')
        if preview_item not in self.items:
            return HttpResponseBadRequest(_('invalid item'))

        regex = r"^" + re.escape(preview_item) + r"_(?P<idx>[\d+])$"
        msgs = {}
        for k, v in request.POST.items():
            # only accept allowed fields
            matched = re.search(regex, k)
            if matched is not None:
                idx = matched.group('idx')
                if idx in self.supported_locale:
                    with translation.override(self.supported_locale[idx]):
                        msgs[self.supported_locale[idx]] = v.format_map(self.placeholders(preview_item))

        return JsonResponse({
            'item': preview_item,
            'msgs': msgs
        })


class TicketSettingsPreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_event_settings'

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
    permission = 'can_change_event_settings'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['providers'] = self.provider_forms

        context['any_enabled'] = False
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.is_enabled:
                context['any_enabled'] = True
                break

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

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

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
                    CachedCombinedTicket.objects.filter(
                        order__event=self.request.event, provider=provider.identifier
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
            return self.form_invalid(form)

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


class EventPermissions(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/event/permissions.html'


class EventLive(EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_event_settings'
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
        for provider in self.request.event.get_payment_providers().values():
            if provider.is_enabled and provider.identifier != 'free':
                has_payment_provider = True
                break

        if has_paid_things and not has_payment_provider:
            issues.append(_('You have configured at least one paid product but have not enabled any payment methods.'))

        if not self.request.event.quotas.exists():
            issues.append(_('You need to configure at least one quota to sell anything.'))

        responses = event_live_issues.send(self.request.event)
        for receiver, response in sorted(responses, key=lambda r: str(r[0])):
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
        if not self.request.user.has_event_permission(self.request.organizer, self.request.event, 'can_view_orders'):
            qs = qs.exclude(content_type=ContentType.objects.get_for_model(Order))
        if not self.request.user.has_event_permission(self.request.organizer, self.request.event, 'can_view_vouchers'):
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
        ctx['userlist'] = self.request.event.logentry_set.order_by().distinct().values('user__id', 'user__email')
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


class EventComment(EventPermissionRequiredMixin, View):
    permission = 'can_change_event_settings'

    def post(self, *args, **kwargs):
        form = CommentForm(self.request.POST)
        if form.is_valid():
            self.request.event.comment = form.cleaned_data.get('comment')
            self.request.event.save()
            self.request.event.log_action('pretix.event.comment', user=self.request.user, data={
                'new_comment': form.cleaned_data.get('comment')
            })
            messages.success(self.request, _('The comment has been updated.'))
        else:
            messages.error(self.request, _('Could not update the comment.'))
        return redirect(self.get_success_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])

    def get_success_url(self) -> str:
        return reverse('control:event.index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })


class TaxList(EventPermissionRequiredMixin, ListView):
    model = TaxRule
    context_object_name = 'taxrules'
    paginate_by = 30
    template_name = 'pretixcontrol/event/tax_index.html'
    permission = 'can_change_event_settings'

    def get_queryset(self):
        return self.request.event.tax_rules.all()


class TaxCreate(EventPermissionRequiredMixin, CreateView):
    model = TaxRule
    form_class = TaxRuleForm
    template_name = 'pretixcontrol/event/tax_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'taxrule'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.tax', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_initial(self):
        return {
            'name': LazyI18nString.from_gettext(ugettext('VAT'))
        }

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new tax rule has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.taxrule.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class TaxUpdate(EventPermissionRequiredMixin, UpdateView):
    model = TaxRule
    form_class = TaxRuleForm
    template_name = 'pretixcontrol/event/tax_edit.html'
    permission = 'can_change_event_settings'
    context_object_name = 'rule'

    def get_object(self, queryset=None) -> TaxRule:
        try:
            return self.request.event.tax_rules.get(
                id=self.kwargs['rule']
            )
        except TaxRule.DoesNotExist:
            raise Http404(_("The requested tax rule does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.taxrule.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.tax', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class TaxDelete(EventPermissionRequiredMixin, DeleteView):
    model = TaxRule
    template_name = 'pretixcontrol/event/tax_delete.html'
    permission = 'can_change_event_settings'
    context_object_name = 'taxrule'

    def get_object(self, queryset=None) -> TaxRule:
        try:
            return self.request.event.tax_rules.get(
                id=self.kwargs['rule']
            )
        except TaxRule.DoesNotExist:
            raise Http404(_("The requested tax rule does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        if self.is_allowed():
            self.object.log_action(action='pretix.event.taxrule.deleted', user=request.user)
            self.object.delete()
            messages.success(self.request, _('The selected tax rule has been deleted.'))
        else:
            messages.error(self.request, _('The selected tax rule can not be deleted.'))
        return redirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.settings.tax', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def is_allowed(self) -> bool:
        o = self.object
        return (
            not OrderFee.objects.filter(tax_rule=o, order__event=self.request.event).exists()
            and not OrderPosition.objects.filter(tax_rule=o, order__event=self.request.event).exists()
            and not self.request.event.items.filter(tax_rule=o).exists()
            and self.request.event.settings.tax_rate_default != o
        )

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.is_allowed()
        return context
