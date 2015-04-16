from collections import OrderedDict
from django.conf import settings
from django.shortcuts import render, redirect
from django.utils.functional import cached_property
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
from . import UpdateView


class EventUpdateForm(VersionedModelForm):

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
            'currency',
            'date_from',
            'date_to',
            'presale_start',
            'presale_end',
        ]


class EventSettingsForm(SettingsForm):
    show_date_to = forms.BooleanField(
        label=_("Show event end date"),
        help_text=_("If disabled, only event's start date will be displayed to the public."),
        required=False
    )
    show_times = forms.BooleanField(
        label=_("Show dates with time"),
        help_text=_("If disabled, the event's start and end date will be displayed without the time of day."),
        required=False
    )
    payment_term_days = forms.IntegerField(
        label='Payment term in days',
        help_text=_("The number of days after placing an order the user has to pay to preserve his reservation."),
    )
    payment_term_last = forms.DateTimeField(
        label='Last date of payments',
        help_text=_("The last date any payments are accepted. This has precedence over the number of "
                    "days configured above."),
        required=False
    )
    payment_term_accept_late = forms.BooleanField(
        label='Accept late payments',
        help_text=_("Accept payments that come after the end of the order's payment term. "
                    "Payments will only be accepted if the regarding quotas have remaining "
                    "capacity. No payments will be accepted after the 'Last date of payments' "
                    "configured above."),
        required=False
    )
    last_order_modification_date = forms.DateTimeField(
        label='Last date of modifications',
        help_text=_("The last date users can modify details of their orders, such as attendee names or "
                    "answers to questions."),
        required=False
    )
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
    )
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Available langauges"),
    )
    locale = forms.ChoiceField(
        choices=settings.LANGUAGES,
        label=_("Default language"),
    )
    user_mail_required = forms.BooleanField(
        label=_("Require e-mail adresses"),
        help_text=_("Require all customers to provide an e-mail address."),
        required=False
    )
    attendee_names_asked = forms.BooleanField(
        label=_("Ask for attendee names"),
        help_text=_("Ask for a name for all tickets which include admission to the event."),
        required=False
    )
    attendee_names_required = forms.BooleanField(
        label=_("Require attendee names"),
        help_text=_("Require customers to fill in the names of all attendees."),
        required=False
    )
    max_items_per_order = forms.IntegerField(
        min_value=1,
        label=_("Maximum number of items per order")
    )
    reservation_time = forms.IntegerField(
        min_value=0,
        label=_("Reservation period"),
        help_text=_("The number of minutes the items in a user's card are reserved for this user."),
    )
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing e-mails")
    )


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
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.settings', kwargs={
            'organizer': self.object.organizer.slug,
            'event': self.object.slug,
        }) + '?success=true'

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


class PaymentMethodForm(SettingsForm):
    """
    This is a SettingsForm, but if fields are set to required=True, validation
    errors are only raised if the payment method is enabled.
    """

    def __init__(self, *args, **kwargs):
        self.settingspref = kwargs.pop('settingspref')
        super().__init__(*args, **kwargs)

    def prepare_fields(self):
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False

    def clean(self):
        cleaned_data = super().clean()
        enabled = cleaned_data.get(self.settingspref + '_enabled') == 'True'
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and (val is None or val == ""):
                print(enabled, k, v)
                self.add_error(k, _('This field is required.'))


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
            provider.form = PaymentMethodForm(
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


def index(request, organizer, event):
    return render(request, 'pretixcontrol/event/index.html', {})
