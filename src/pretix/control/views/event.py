import json
import re
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.db import transaction
from django.db.models import ProtectedError
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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

from pretix.base.channels import get_all_sales_channels
from pretix.base.i18n import LazyCurrencyNumber
from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, Event, LogEntry, Order, RequiredAction,
    TaxRule, Voucher,
)
from pretix.base.models.event import EventMetaValue
from pretix.base.services import tickets
from pretix.base.services.invoices import build_preview_invoice_pdf
from pretix.base.signals import register_ticket_outputs
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.control.forms.event import (
    CancelSettingsForm, CommentForm, DisplaySettingsForm, EventDeleteForm,
    EventMetaValueForm, EventSettingsForm, EventUpdateForm,
    InvoiceSettingsForm, MailSettingsForm, PaymentSettingsForm, ProviderForm,
    QuickSetupForm, QuickSetupProductFormSet, TaxRuleForm, TaxRuleLineFormSet,
    TicketSettingsForm, WidgetCodeForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.database import rolledback_transaction
from pretix.helpers.urls import build_absolute_uri
from pretix.multidomain.urlreverse import get_domain
from pretix.plugins.stripe.payment import StripeSettingsHolder
from pretix.presale.style import regenerate_css

from ..logdisplay import OVERVIEW_BLACKLIST
from . import CreateView, PaginationMixin, UpdateView


class EventSettingsViewMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_event_settings'] = True
        return ctx


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
                f.instance.delete()


class EventUpdate(EventSettingsViewMixin, EventPermissionRequiredMixin, MetaDataEditorMixin, UpdateView):
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.has_active_staff_session(self.request.session.session_key):
            kwargs['change_slug'] = True
        return kwargs

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


class EventPlugins(EventSettingsViewMixin, EventPermissionRequiredMixin, TemplateView, SingleObjectMixin):
    model = Event
    context_object_name = 'event'
    permission = 'can_change_event_settings'
    template_name = 'pretixcontrol/event/plugins.html'

    def get_object(self, queryset=None) -> Event:
        return self.request.event

    def get_context_data(self, *args, **kwargs) -> dict:
        from pretix.base.plugins import get_all_plugins

        context = super().get_context_data(*args, **kwargs)
        context['plugins'] = [p for p in get_all_plugins(self.object) if not p.name.startswith('.')
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

        plugins_available = {
            p.module: p for p in get_all_plugins(self.object)
            if not p.name.startswith('.') and getattr(p, 'visible', True)
        }

        with transaction.atomic():
            allow_restricted = request.user.has_active_staff_session(request.session.session_key)

            for key, value in request.POST.items():
                if key.startswith("plugin:"):
                    module = key.split(":")[1]
                    if value == "enable" and module in plugins_available:
                        if getattr(plugins_available[module], 'restricted', False):
                            if not allow_restricted:
                                continue

                        self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                                      data={'plugin': module})
                        self.object.enable_plugin(module, allow_restricted=allow_restricted)
                    else:
                        self.request.event.log_action('pretix.event.plugins.disabled', user=self.request.user,
                                                      data={'plugin': module})
                        self.object.disable_plugin(module)
            self.object.save()
        messages.success(self.request, _('Your changes have been saved.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.settings.plugins', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        })


class PaymentProviderSettings(EventSettingsViewMixin, EventPermissionRequiredMixin, TemplateView, SingleObjectMixin):
    model = Event
    context_object_name = 'event'
    permission = 'can_change_event_settings'
    template_name = 'pretixcontrol/event/payment_provider.html'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.payment', kwargs={
            'organizer': self.get_object().organizer.slug,
            'event': self.get_object().slug,
        })

    @cached_property
    def object(self):
        return self.request.event

    def get_object(self, queryset=None):
        return self.object

    @cached_property
    def provider(self):
        provider = self.request.event.get_payment_providers().get(self.kwargs['provider'])
        return provider

    @cached_property
    def form(self):
        form = ProviderForm(
            obj=self.request.event,
            settingspref=self.provider.settings.get_prefix(),
            data=(self.request.POST if self.request.method == 'POST' else None),
            provider=self.provider
        )
        form.fields = OrderedDict(
            [
                ('%s%s' % (self.provider.settings.get_prefix(), k), v)
                for k, v in self.provider.settings_form_fields.items()
            ]
        )
        form.prepare_fields()
        return form

    def dispatch(self, request, *args, **kwargs):
        if not self.provider:
            messages.error(self.request, _('This payment provider does not exist or the respective plugin is '
                                           'disabled.'))
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def settings_content(self):
        return self.provider.settings_content_render(self.request)

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['form'] = self.form
        context['provider'] = self.provider
        context['settings_content'] = self.settings_content
        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            if self.form.has_changed():
                self.request.event.log_action(
                    'pretix.event.payment.provider.' + self.provider.identifier, user=self.request.user, data={
                        k: self.form.cleaned_data.get(k) for k in self.form.changed_data
                    }
                )
                self.form.save()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.get(request)


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

    def _save_decoupled(self, form):
        # Save fields that are currently only set via the organizer but should be decoupled
        fields = set()
        for f in self.request.POST.getlist("decouple"):
            fields |= set(f.split(","))
        for f in fields:
            if f not in form.fields:
                continue
            if f not in self.request.event.settings._cache():
                self.request.event.settings.set(f, self.request.event.settings.get(f))

    def form_success(self):
        pass

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            form.save()
            self._save_decoupled(form)
            self.form_success()
            if form.has_changed():
                self.request.event.log_action(
                    'pretix.event.settings', user=self.request.user, data={
                        k: (form.cleaned_data.get(k).name
                            if isinstance(form.cleaned_data.get(k), File)
                            else form.cleaned_data.get(k))
                        for k in form.changed_data
                    }
                )
            self.form_success()
            messages.success(self.request, _('Your changes have been saved.'))
            return redirect(self.get_success_url())
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.render_to_response(self.get_context_data(form=form))


class PaymentSettings(EventSettingsViewMixin, EventSettingsFormView):
    template_name = 'pretixcontrol/event/payment.html'
    form_class = PaymentSettingsForm
    permission = 'can_change_event_settings'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.payment', kwargs={
            'organizer': self.request.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['providers'] = sorted(
            [p for p in self.request.event.get_payment_providers().values()
             if not p.is_implicit and (p.settings_form_fields or p.settings_content_render(self.request))],
            key=lambda s: s.verbose_name
        )
        for p in context['providers']:
            p.show_enabled = p.is_enabled
            if p.is_meta:
                p.show_enabled = p.settings._enabled in (True, 'True')
        return context


class InvoiceSettings(EventSettingsViewMixin, EventSettingsFormView):
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


class CancelSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = CancelSettingsForm
    template_name = 'pretixcontrol/event/cancel.html'
    permission = 'can_change_event_settings'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.cancel', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['gets_notification'] = self.request.user.notifications_send and (
            (
                self.request.user.notification_settings.filter(
                    event=self.request.event,
                    action_type='pretix.event.order.refund.requested',
                    enabled=True
                ).exists()
            ) or (
                self.request.user.notification_settings.filter(
                    event__isnull=True,
                    action_type='pretix.event.order.refund.requested',
                    enabled=True
                ).exists() and not
                self.request.user.notification_settings.filter(
                    event=self.request.event,
                    action_type='pretix.event.order.refund.requested',
                    enabled=False
                ).exists()
            )
        )
        return ctx


class InvoicePreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_event_settings'

    def get(self, request, *args, **kwargs):
        fname, ftype, fcontent = build_preview_invoice_pdf(request.event)
        resp = HttpResponse(fcontent, content_type=ftype)
        resp['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)
        return resp


class DisplaySettings(EventSettingsViewMixin, EventSettingsFormView):
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
            self._save_decoupled(form)
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


class MailSettings(EventSettingsViewMixin, EventSettingsFormView):
    model = Event
    form_class = MailSettingsForm
    template_name = 'pretixcontrol/event/mail.html'
    permission = 'can_change_event_settings'

    def get_success_url(self) -> str:
        return reverse('control:event.settings.mail', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['renderers'] = self.request.event.get_html_mail_renderers()
        return ctx

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
                    messages.warning(self.request, _('An error occurred while contacting the SMTP server: %s') % str(e))
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
            'payment_info': _('{} has been transferred to account <9999-9999-9999-9999> at {}').format(
                money_filter(Decimal('42.23'), self.request.event.currency),
                date_format(now(), 'SHORT_DATETIME_FORMAT'))
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
    def meta_properties(self):
        return [p.name for p in self.request.organizer.meta_properties.all()]

    @cached_property
    def items(self):
        kv = {
            'mail_text_order_placed': ['total', 'currency', 'date', 'invoice_company', 'total_with_currency',
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
                                            'invoice_name', 'invoice_company'],
            'mail_text_download_reminder': ['event', 'url'],
            'mail_text_order_placed_require_approval': ['total', 'currency', 'date', 'invoice_company',
                                                        'total_with_currency', 'event', 'url', 'invoice_name'],
            'mail_text_order_approved': ['total', 'currency', 'date', 'invoice_company',
                                         'total_with_currency', 'event', 'url', 'invoice_name'],
            'mail_text_order_denied': ['total', 'currency', 'date', 'invoice_company',
                                       'total_with_currency', 'event', 'url', 'invoice_name'],
        }
        for v in kv.values():
            for p in self.meta_properties:
                v.append('meta_' + p)
        return kv

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
        d = {
            'event': self.request.event.name,
            'total': 42.23,
            'total_with_currency': LazyCurrencyNumber(42.23, self.request.event.currency),
            'currency': self.request.event.currency,
            'url': self.generate_order_url(user_orders[0]['code'], user_orders[0]['secret']),
            'orders': '\n'.join(orders),
            'hours': self.request.event.settings.waiting_list_hours,
            'product': _('Sample Admission Ticket'),
            'code': '68CYU2H6ZTP3WLK5',
            'invoice_name': _('John Doe'),
            'invoice_company': _('Sample Corporation'),
            'common': _('An individial text with a reason can be inserted here.'),
            'payment_info': _('Please transfer money to this bank account: 9999-9999-9999-9999'),
        }
        for k, v in self.request.event.meta_data.items():
            d['meta_' + k] = v
        return d

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
                        msgs[self.supported_locale[idx]] = markdown_compile_email(
                            v.format_map(self.placeholders(preview_item))
                        )

        return JsonResponse({
            'item': preview_item,
            'msgs': msgs
        })


class MailSettingsRendererPreview(MailSettingsPreview):
    permission = 'can_change_event_settings'

    def post(self, request, *args, **kwargs):
        return HttpResponse(status=405)

    def get(self, request, *args, **kwargs):
        v = str(request.event.settings.mail_text_order_placed)
        v = v.format_map(self.placeholders('mail_text_order_placed'))
        renderers = request.event.get_html_mail_renderers()
        if request.GET.get('renderer') in renderers:
            with rolledback_transaction():
                order = request.event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                                    expires=now(), code="PREVIEW", total=119)
                item = request.event.items.create(name=ugettext("Sample product"), default_price=42.23,
                                                  description=ugettext("Sample product description"))
                order.positions.create(item=item, attendee_name_parts={'_legacy': ugettext("John Doe")},
                                       price=item.default_price)
                v = renderers[request.GET.get('renderer')].render(
                    v,
                    str(request.event.settings.mail_text_signature),
                    ugettext('Your order: %(code)s') % {'code': order.code},
                    order
                )
                r = HttpResponse(v, content_type='text/html')
                r._csp_ignore = True
                return r
        else:
            raise Http404(_('Unknown e-mail renderer.'))


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


class TicketSettings(EventSettingsViewMixin, EventPermissionRequiredMixin, FormView):
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


class EventPermissions(EventSettingsViewMixin, EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/event/permissions.html'


class EventLive(EventPermissionRequiredMixin, TemplateView):
    permission = 'can_change_event_settings'
    template_name = 'pretixcontrol/event/live.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['issues'] = self.request.event.live_issues
        ctx['actual_orders'] = self.request.event.orders.filter(testmode=False).exists()
        return ctx

    def post(self, request, *args, **kwargs):
        if request.POST.get("live") == "true" and not self.request.event.live_issues:
            with transaction.atomic():
                request.event.live = True
                request.event.save()
                self.request.event.log_action(
                    'pretix.event.live.activated', user=self.request.user, data={}
                )
            messages.success(self.request, _('Your shop is live now!'))
        elif request.POST.get("live") == "false":
            with transaction.atomic():
                request.event.live = False
                request.event.save()
                self.request.event.log_action(
                    'pretix.event.live.deactivated', user=self.request.user, data={}
                )
            messages.success(self.request, _('We\'ve taken your shop down. You can re-enable it whenever you want!'))
        elif request.POST.get("testmode") == "true":
            with transaction.atomic():
                request.event.testmode = True
                request.event.save()
                self.request.event.log_action(
                    'pretix.event.testmode.activated', user=self.request.user, data={}
                )
            messages.success(self.request, _('Your shop is now in test mode!'))
        elif request.POST.get("testmode") == "false":
            with transaction.atomic():
                request.event.testmode = False
                request.event.save()
                self.request.event.log_action(
                    'pretix.event.testmode.deactivated', user=self.request.user, data={
                        'delete': (request.POST.get("delete") == "yes")
                    }
                )
            request.event.cache.delete('complain_testmode_orders')
            if request.POST.get("delete") == "yes":
                try:
                    with transaction.atomic():
                        for order in request.event.orders.filter(testmode=True):
                            order.gracefully_delete(user=self.request.user)
                except ProtectedError:
                    messages.error(self.request, _('An order could not be deleted as some constraints (e.g. data '
                                                   'created by plug-ins) do not allow it.'))
                else:
                    request.event.cache.set('complain_testmode_orders', False, 30)
            request.event.cartposition_set.filter(addon_to__isnull=False).delete()
            request.event.cartposition_set.all().delete()
            messages.success(self.request, _('We\'ve disabled test mode for you. Let\'s sell some real tickets!'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.live', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug
        })


class EventDelete(EventPermissionRequiredMixin, FormView):
    permission = 'can_change_event_settings'
    template_name = 'pretixcontrol/event/delete.html'
    form_class = EventDeleteForm

    def post(self, request, *args, **kwargs):
        if not self.request.event.allow_delete():
            messages.error(self.request, _('This event can not be deleted.'))
            return self.get(self.request, *self.args, **self.kwargs)
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['event'] = self.request.event
        return kwargs

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.request.organizer.log_action(
                    'pretix.event.deleted', user=self.request.user,
                    data={
                        'event_id': self.request.event.pk,
                        'name': str(self.request.event.name),
                        'logentries': list(self.request.event.logentry_set.values_list('pk', flat=True))
                    }
                )
                self.request.event.delete_sub_objects()
                self.request.event.delete()
            messages.success(self.request, _('The event has been deleted.'))
            return redirect(self.get_success_url())
        except ProtectedError:
            messages.error(self.request, _('The event could not be deleted as some constraints (e.g. data created by '
                                           'plug-ins) do not allow it.'))
            return self.get(self.request, *self.args, **self.kwargs)

    def get_success_url(self) -> str:
        return reverse('control:index')


class EventLog(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixcontrol/event/logs.html'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        qs = self.request.event.logentry_set.all().select_related(
            'user', 'content_type', 'api_token', 'oauth_application', 'device'
        ).order_by('-datetime')
        qs = qs.exclude(action_type__in=OVERVIEW_BLACKLIST)
        if not self.request.user.has_event_permission(self.request.organizer, self.request.event, 'can_view_orders',
                                                      request=self.request):
            qs = qs.exclude(content_type=ContentType.objects.get_for_model(Order))
        if not self.request.user.has_event_permission(self.request.organizer, self.request.event, 'can_view_vouchers',
                                                      request=self.request):
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


class TaxList(EventSettingsViewMixin, EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = TaxRule
    context_object_name = 'taxrules'
    template_name = 'pretixcontrol/event/tax_index.html'
    permission = 'can_change_event_settings'

    def get_queryset(self):
        return self.request.event.tax_rules.all()


class TaxCreate(EventSettingsViewMixin, EventPermissionRequiredMixin, CreateView):
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

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid() and self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @cached_property
    def formset(self):
        return TaxRuleLineFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        form.instance.custom_rules = json.dumps([
            f.cleaned_data for f in self.formset if f not in self.formset.deleted_forms
        ])
        messages.success(self.request, _('The new tax rule has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.taxrule.added', user=self.request.user, data=dict(form.cleaned_data))
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class TaxUpdate(EventSettingsViewMixin, EventPermissionRequiredMixin, UpdateView):
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

    def post(self, request, *args, **kwargs):
        self.object = self.get_object(self.get_queryset())
        form = self.get_form()
        if form.is_valid() and self.formset.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @cached_property
    def formset(self):
        return TaxRuleLineFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            initial=json.loads(self.object.custom_rules) if self.object.custom_rules else []
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = self.formset
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        form.instance.custom_rules = json.dumps([
            f.cleaned_data for f in self.formset if f not in self.formset.deleted_forms
        ])
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


class TaxDelete(EventSettingsViewMixin, EventPermissionRequiredMixin, DeleteView):
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
        if self.object.allow_delete():
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

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.object.allow_delete()
        return context


class WidgetSettings(EventSettingsViewMixin, EventPermissionRequiredMixin, FormView):
    template_name = 'pretixcontrol/event/widget.html'
    permission = 'can_change_event_settings'
    form_class = WidgetCodeForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def form_valid(self, form):
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['valid'] = True
        return self.render_to_response(ctx)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['urlprefix'] = settings.SITE_URL
        domain = get_domain(self.request.organizer)
        if domain:
            siteurlsplit = urlsplit(settings.SITE_URL)
            if siteurlsplit.port and siteurlsplit.port not in (80, 443):
                domain = '%s:%d' % (domain, siteurlsplit.port)
            ctx['urlprefix'] = '%s://%s' % (siteurlsplit.scheme, domain)
        return ctx


class QuickSetupView(FormView):
    template_name = 'pretixcontrol/event/quick_setup.html'
    permission = 'can_change_event_settings'
    form_class = QuickSetupForm

    def dispatch(self, request, *args, **kwargs):
        if request.event.items.exists() or request.event.quotas.exists():
            messages.info(request, _('Your event is not empty, you need to set it up manually.'))
            return redirect(reverse('control:event.index', kwargs={
                'organizer': request.event.organizer.slug,
                'event': request.event.slug
            }))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['formset'] = self.formset
        return ctx

    def get_initial(self):
        return {
            'waiting_list_enabled': True,
            'ticket_download': True,
            'contact_mail': self.request.event.settings.contact_mail,
            'imprint_url': self.request.event.settings.imprint_url,
        }

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid() and self.formset.is_valid():
            return self.form_valid(form)
        else:
            messages.error(self.request, _('We could not save your changes. See below for details.'))
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        plugins_active = self.request.event.get_plugins()
        if form.cleaned_data['ticket_download']:
            if 'pretix.plugins.ticketoutputpdf' not in plugins_active:
                self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                              data={'plugin': 'pretix.plugins.ticketoutputpdf'})
                plugins_active.append('pretix.plugins.ticketoutputpdf')

            self.request.event.settings.ticket_download = True
            self.request.event.settings.ticketoutput_pdf__enabled = True

            try:
                import pretix_passbook  # noqa
            except ImportError:
                pass
            else:
                if 'pretix_passbook' not in plugins_active:
                    self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                                  data={'plugin': 'pretix_passbook'})
                    plugins_active.append('pretix_passbook')
                self.request.event.settings.ticketoutput_passbook__enabled = True

        if form.cleaned_data['payment_banktransfer__enabled']:
            if 'pretix.plugins.banktransfer' not in plugins_active:
                self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                              data={'plugin': 'pretix.plugins.banktransfer'})
                plugins_active.append('pretix.plugins.banktransfer')
            self.request.event.settings.payment_banktransfer__enabled = True
            for f in ('bank_details', 'bank_details_type', 'bank_details_sepa_name', 'bank_details_sepa_iban',
                      'bank_details_sepa_bic', 'bank_details_sepa_bank'):
                self.request.event.settings.set(
                    'payment_banktransfer_%s' % f,
                    form.cleaned_data['payment_banktransfer_%s' % f]
                )

        if form.cleaned_data.get('payment_stripe__enabled', None):
            if 'pretix.plugins.stripe' not in plugins_active:
                self.request.event.log_action('pretix.event.plugins.enabled', user=self.request.user,
                                              data={'plugin': 'pretix.plugins.stripe'})
                plugins_active.append('pretix.plugins.stripe')

        self.request.event.settings.show_quota_left = form.cleaned_data['show_quota_left']
        self.request.event.settings.waiting_list_enabled = form.cleaned_data['waiting_list_enabled']
        self.request.event.settings.attendee_names_required = form.cleaned_data['attendee_names_required']
        self.request.event.settings.contact_mail = form.cleaned_data['contact_mail']
        self.request.event.settings.imprint_url = form.cleaned_data['imprint_url']
        self.request.event.log_action('pretix.event.settings', user=self.request.user, data={
            k: self.request.event.settings.get(k) for k in form.changed_data
        })

        items = []
        category = None
        tax_rule = self.request.event.tax_rules.first()
        if any(f not in self.formset.deleted_forms for f in self.formset):
            category = self.request.event.categories.create(
                name=LazyI18nString.from_gettext(ugettext('Tickets'))
            )
            category.log_action('pretix.event.category.added', data={'name': ugettext('Tickets')},
                                user=self.request.user)

        subevent = self.request.event.subevents.first()
        for i, f in enumerate(self.formset):
            if f in self.formset.deleted_forms or not f.has_changed():
                continue

            item = self.request.event.items.create(
                name=f.cleaned_data['name'],
                category=category,
                active=True,
                default_price=f.cleaned_data['default_price'] or 0,
                tax_rule=tax_rule,
                admission=True,
                position=i,
                sales_channels=[k for k in get_all_sales_channels().keys()]
            )
            item.log_action('pretix.event.item.added', user=self.request.user, data=dict(f.cleaned_data))
            if f.cleaned_data['quota'] or not form.cleaned_data['total_quota']:
                quota = self.request.event.quotas.create(
                    name=str(f.cleaned_data['name']),
                    subevent=subevent,
                    size=f.cleaned_data['quota'],
                )
                quota.log_action('pretix.event.quota.added', user=self.request.user, data=dict(f.cleaned_data))
                quota.items.add(item)
            items.append(item)

        if form.cleaned_data['total_quota']:
            quota = self.request.event.quotas.create(
                name=ugettext('Tickets'),
                size=form.cleaned_data['total_quota'],
                subevent=subevent,
            )
            quota.log_action('pretix.event.quota.added', user=self.request.user, data={
                'name': ugettext('Tickets'),
                'size': quota.size
            })
            quota.items.add(*items)

        self.request.event.plugins = ",".join(plugins_active)
        self.request.event.save()
        messages.success(self.request, _('Your changes have been saved. You can now go on with looking at the details '
                                         'or take your event live to start selling!'))

        if form.cleaned_data.get('payment_stripe__enabled', False):
            self.request.session['payment_stripe_oauth_enable'] = True
            return redirect(StripeSettingsHolder(self.request.event).get_connect_url(self.request))

        return redirect(reverse('control:event.index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        }))

    @cached_property
    def formset(self):
        return QuickSetupProductFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            event=self.request.event,
            initial=[
                {
                    'name': LazyI18nString.from_gettext(ugettext('Regular ticket')),
                    'default_price': Decimal('35.00'),
                    'quota': 100,
                },
                {
                    'name': LazyI18nString.from_gettext(ugettext('Reduced ticket')),
                    'default_price': Decimal('29.00'),
                    'quota': 50,
                },
            ] if self.request.method != "POST" else []
        )
