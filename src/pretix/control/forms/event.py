from urllib.parse import urlencode

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator, MinValueValidator, RegexValidator, validate_email,
)
from django.db.models import Q
from django.forms import formset_factory
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.timezone import get_current_timezone_name
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from django_countries import Countries, countries
from django_countries.fields import LazyTypedChoiceField
from i18nfield.forms import (
    I18nForm, I18nFormField, I18nFormSetMixin, I18nTextarea, I18nTextInput,
)
from pytz import common_timezones, timezone

from pretix.base.channels import get_all_sales_channels
from pretix.base.email import get_available_placeholders
from pretix.base.forms import I18nModelForm, PlaceholderValidator, SettingsForm
from pretix.base.models import Event, Organizer, TaxRule, Team
from pretix.base.models.event import EventMetaValue, SubEvent
from pretix.base.reldate import RelativeDateField, RelativeDateTimeField
from pretix.base.settings import (
    PERSON_NAME_SCHEMES, PERSON_NAME_TITLE_GROUPS, validate_settings,
)
from pretix.control.forms import (
    ExtFileField, FontSelect, MultipleLanguagesWidget, SlugWidget,
    SplitDateTimeField, SplitDateTimePickerWidget,
)
from pretix.control.forms.widgets import Select2
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.plugins.banktransfer.payment import BankTransfer
from pretix.presale.style import get_fonts


class EventWizardFoundationForm(forms.Form):
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        widget=MultipleLanguagesWidget,
        help_text=_('Choose all languages that your event should be available in.')
    )
    has_subevents = forms.BooleanField(
        label=_("This is an event series"),
        help_text=_('Only recommended for advanced users. If this feature is enabled, this will not only be a '
                    'single event but a series of very similar events that are handled within a single shop. '
                    'The single events inside the series can only differ in date, time, location, prices and '
                    'quotas, but not in other settings, and buying tickets across multiple of these events at '
                    'the same time is possible. You cannot change this setting for this event later.'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.session = kwargs.pop('session')
        super().__init__(*args, **kwargs)
        qs = Organizer.objects.all()
        if not self.user.has_active_staff_session(self.session.session_key):
            qs = qs.filter(
                id__in=self.user.teams.filter(can_create_events=True).values_list('organizer', flat=True)
            )
        self.fields['organizer'] = forms.ModelChoiceField(
            label=_("Organizer"),
            queryset=qs,
            widget=Select2(
                attrs={
                    'data-model-select2': 'generic',
                    'data-select2-url': reverse('control:organizers.select2') + '?can_create=1',
                    'data-placeholder': _('Organizer')
                }
            ),
            empty_label=None,
            required=True
        )
        self.fields['organizer'].widget.choices = self.fields['organizer'].choices

        if len(self.fields['organizer'].choices) == 1:
            self.fields['organizer'].initial = self.fields['organizer'].queryset.first()


class EventWizardBasicsForm(I18nModelForm):
    error_messages = {
        'duplicate_slug': _("You already used this slug for a different event. Please choose a new one."),
    }
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Event timezone"),
    )
    locale = forms.ChoiceField(
        choices=settings.LANGUAGES,
        label=_("Default language"),
    )
    tax_rate = forms.DecimalField(
        label=_("Sales tax rate"),
        help_text=_("Do you need to pay sales tax on your tickets? In this case, please enter the applicable tax rate "
                    "here in percent. If you have a more complicated tax situation, you can add more tax rates and "
                    "detailed configuration later."),
        required=False
    )

    team = forms.ModelChoiceField(
        label=_("Grant access to team"),
        help_text=_("You are allowed to create events under this organizer, however you do not have permission "
                    "to edit all events under this organizer. Please select one of your existing teams that will"
                    " be granted access to this event."),
        queryset=Team.objects.none(),
        required=False,
        empty_label=_('Create a new team for this event with me as the only member')
    )

    class Meta:
        model = Event
        fields = [
            'name',
            'slug',
            'currency',
            'date_from',
            'date_to',
            'presale_start',
            'presale_end',
            'location',
            'geo_lat',
            'geo_lon',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_basics-date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_basics-presale_start_0'}),
            'slug': SlugWidget,
        }

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.locales = kwargs.get('locales')
        self.has_subevents = kwargs.pop('has_subevents')
        self.user = kwargs.pop('user')
        kwargs.pop('session')
        super().__init__(*args, **kwargs)
        if 'timezone' not in self.initial:
            self.initial['timezone'] = get_current_timezone_name()
        self.fields['locale'].choices = [(a, b) for a, b in settings.LANGUAGES if a in self.locales]
        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['location'].widget.attrs['placeholder'] = _(
            'Sample Conference Center\nHeidelberg, Germany'
        )
        self.fields['slug'].widget.prefix = build_absolute_uri(self.organizer, 'presale:organizer.index')
        if self.has_subevents:
            del self.fields['presale_start']
            del self.fields['presale_end']

        if self.has_control_rights(self.user, self.organizer):
            del self.fields['team']
        else:
            self.fields['team'].queryset = self.user.teams.filter(organizer=self.organizer)
            if not self.organizer.settings.get("event_team_provisioning", True, as_type=bool):
                self.fields['team'].required = True
                self.fields['team'].empty_label = None
                self.fields['team'].initial = 0

    def clean(self):
        data = super().clean()
        if data.get('locale') not in self.locales:
            raise ValidationError({
                'locale': _('Your default locale must also be enabled for your event (see box above).')
            })
        if data.get('timezone') not in common_timezones:
            raise ValidationError({
                'timezone': _('Your default locale must be specified.')
            })

        # change timezone
        zone = timezone(data.get('timezone'))
        data['date_from'] = self.reset_timezone(zone, data.get('date_from'))
        data['date_to'] = self.reset_timezone(zone, data.get('date_to'))
        data['presale_start'] = self.reset_timezone(zone, data.get('presale_start'))
        data['presale_end'] = self.reset_timezone(zone, data.get('presale_end'))
        return data

    @staticmethod
    def reset_timezone(tz, dt):
        return tz.localize(dt.replace(tzinfo=None)) if dt is not None else None

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if Event.objects.filter(slug__iexact=slug, organizer=self.organizer).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug'
            )
        return slug

    @staticmethod
    def has_control_rights(user, organizer):
        return user.teams.filter(
            organizer=organizer, all_events=True, can_change_event_settings=True, can_change_items=True,
            can_change_orders=True, can_change_vouchers=True
        ).exists()


class EventChoiceMixin:
    def label_from_instance(self, obj):
        return mark_safe('{}<br /><span class="text-muted">{} · {}</span>'.format(
            escape(str(obj)),
            obj.get_date_range_display() if not obj.has_subevents else _("Event series"),
            obj.slug
        ))


class EventChoiceField(forms.ModelChoiceField):
    pass


class SafeEventMultipleChoiceField(EventChoiceMixin, forms.ModelMultipleChoiceField):
    def __init__(self, queryset, *args, **kwargs):
        queryset = queryset.model.objects.none()
        super().__init__(queryset, *args, **kwargs)


class EventWizardCopyForm(forms.Form):

    @staticmethod
    def copy_from_queryset(user, session):
        if user.has_active_staff_session(session.session_key):
            return Event.objects.all()
        return Event.objects.filter(
            Q(organizer_id__in=user.teams.filter(
                all_events=True, can_change_event_settings=True, can_change_items=True
            ).values_list('organizer', flat=True)) | Q(id__in=user.teams.filter(
                can_change_event_settings=True, can_change_items=True
            ).values_list('limit_events__id', flat=True))
        )

    def __init__(self, *args, **kwargs):
        kwargs.pop('organizer')
        kwargs.pop('locales')
        self.session = kwargs.pop('session')
        kwargs.pop('has_subevents')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

        self.fields['copy_from_event'] = EventChoiceField(
            label=_("Copy configuration from"),
            queryset=EventWizardCopyForm.copy_from_queryset(self.user, self.session),
            widget=Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:events.typeahead') + '?can_copy=1',
                    'data-placeholder': _('Do not copy')
                }
            ),
            empty_label=_('Do not copy'),
            required=False
        )
        self.fields['copy_from_event'].widget.choices = self.fields['copy_from_event'].choices


class EventMetaValueForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.property = kwargs.pop('property')
        super().__init__(*args, **kwargs)
        self.fields['value'].required = False
        self.fields['value'].widget.attrs['placeholder'] = self.property.default
        self.fields['value'].widget.attrs['data-typeahead-url'] = (
            reverse('control:events.meta.typeahead') + '?' + urlencode({
                'property': self.property.name,
                'organizer': self.property.organizer.slug,
            })
        )

    class Meta:
        model = EventMetaValue
        fields = ['value']
        widgets = {
            'value': forms.TextInput()
        }


class EventUpdateForm(I18nModelForm):

    def __init__(self, *args, **kwargs):
        self.change_slug = kwargs.pop('change_slug', False)
        super().__init__(*args, **kwargs)
        if not self.change_slug:
            self.fields['slug'].widget.attrs['readonly'] = 'readonly'
        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['location'].widget.attrs['placeholder'] = _(
            'Sample Conference Center\nHeidelberg, Germany'
        )

    def clean_slug(self):
        if self.change_slug:
            return self.cleaned_data['slug']
        return self.instance.slug

    class Meta:
        model = Event
        localized_fields = '__all__'
        fields = [
            'name',
            'slug',
            'currency',
            'date_from',
            'date_to',
            'date_admission',
            'is_public',
            'presale_start',
            'presale_end',
            'location',
            'geo_lat',
            'geo_lon',
        ]
        field_classes = {
            'date_from': SplitDateTimeField,
            'date_to': SplitDateTimeField,
            'date_admission': SplitDateTimeField,
            'presale_start': SplitDateTimeField,
            'presale_end': SplitDateTimeField,
        }
        widgets = {
            'date_from': SplitDateTimePickerWidget(),
            'date_to': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_date_from_0'}),
            'date_admission': SplitDateTimePickerWidget(attrs={'data-date-default': '#id_date_from_0'}),
            'presale_start': SplitDateTimePickerWidget(),
            'presale_end': SplitDateTimePickerWidget(attrs={'data-date-after': '#id_presale_start_0'}),
        }


class EventSettingsForm(SettingsForm):
    last_order_modification_date = RelativeDateTimeField(
        label=_('Last date of modifications'),
        help_text=_("The last date users can modify details of their orders, such as attendee names or "
                    "answers to questions. If you use the event series feature and an order contains tickets for "
                    "multiple event dates, the earliest date will be used."),
        required=False,
    )
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Event timezone"),
    )
    name_scheme = forms.ChoiceField(
        label=_("Name format"),
        help_text=_("This defines how pretix will ask for human names. Changing this after you already received "
                    "orders might lead to unexpected behaviour when sorting or changing names."),
        required=True,
    )
    name_scheme_titles = forms.ChoiceField(
        label=_("Allowed titles"),
        help_text=_("If the naming scheme you defined above allows users to input a title, you can use this to "
                    "restrict the set of selectable titles."),
        required=False,
    )
    logo_image = ExtFileField(
        label=_('Logo image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your events name and date '
                    'in the page header. We will show your logo with a maximal height of 120 pixels.')
    )
    og_image = ExtFileField(
        label=_('Social media image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('This picture will be used as a preview if you post links to your ticket shop on social media. '
                    'Facebook advises to use a picture size of 1200 x 630 pixels, however some platforms like '
                    'WhatsApp and Reddit only show a square preview, so we recommend to make sure it still looks good '
                    'only the center square is shown. If you do not fill this, we will use the logo given above.')
    )
    primary_color = forms.CharField(
        label=_("Primary color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    theme_color_success = forms.CharField(
        label=_("Accent color for success"),
        help_text=_("We strongly suggest to use a shade of green."),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    theme_color_danger = forms.CharField(
        label=_("Accent color for errors"),
        help_text=_("We strongly suggest to use a dark shade of red."),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    primary_font = forms.ChoiceField(
        label=_('Font'),
        choices=[
            ('Open Sans', 'Open Sans')
        ],
        widget=FontSelect,
        help_text=_('Only respected by modern browsers.')
    )

    auto_fields = [
        'imprint_url',
        'checkout_email_helptext',
        'presale_has_ended_text',
        'voucher_explanation_text',
        'show_date_to',
        'show_times',
        'show_items_outside_presale_period',
        'display_net_prices',
        'presale_start_show_date',
        'locales',
        'locale',
        'show_quota_left',
        'waiting_list_enabled',
        'waiting_list_hours',
        'waiting_list_auto',
        'max_items_per_order',
        'reservation_time',
        'contact_mail',
        'show_variations_expanded',
        'hide_sold_out',
        'meta_noindex',
        'redirect_to_checkout_directly',
        'frontpage_subevent_ordering',
        'frontpage_text',
        'attendee_names_asked',
        'attendee_names_required',
        'attendee_emails_asked',
        'attendee_emails_required',
        'confirm_text',
        'order_email_asked_twice',
    ]

    def clean(self):
        data = super().clean()
        settings_dict = self.event.settings.freeze()
        settings_dict.update(data)
        validate_settings(self.event, data)
        return data

    def __init__(self, *args, **kwargs):
        self.event = kwargs['obj']
        super().__init__(*args, **kwargs)
        self.fields['confirm_text'].widget.attrs['rows'] = '3'
        self.fields['confirm_text'].widget.attrs['placeholder'] = _(
            'e.g. I hereby confirm that I have read and agree with the event organizer\'s terms of service '
            'and agree with them.'
        )
        self.fields['name_scheme'].choices = (
            (k, _('Ask for {fields}, display like {example}').format(
                fields=' + '.join(str(vv[1]) for vv in v['fields']),
                example=v['concatenation'](v['sample'])
            ))
            for k, v in PERSON_NAME_SCHEMES.items()
        )
        self.fields['name_scheme_titles'].choices = [('', _('Free text input'))] + [
            (k, '{scheme}: {samples}'.format(
                scheme=v[0],
                samples=', '.join(v[1])
            ))
            for k, v in PERSON_NAME_TITLE_GROUPS.items()
        ]
        if not self.event.has_subevents:
            del self.fields['frontpage_subevent_ordering']
        self.fields['primary_font'].choices += [
            (a, {"title": a, "data": v}) for a, v in get_fonts().items()
        ]


class CancelSettingsForm(SettingsForm):
    cancel_allow_user = forms.BooleanField(
        label=_("Customers can cancel their unpaid orders"),
        required=False
    )
    cancel_allow_user_until = RelativeDateTimeField(
        label=_("Do not allow cancellations after"),
        required=False
    )
    cancel_allow_user_paid = forms.BooleanField(
        label=_("Customers can cancel their paid orders"),
        help_text=_("Paid money will be automatically paid back if the payment method allows it. "
                    "Otherwise, a manual refund will be created for you to process manually."),
        required=False
    )
    cancel_allow_user_paid_keep = forms.DecimalField(
        label=_("Keep a fixed cancellation fee"),
        required=False
    )
    cancel_allow_user_paid_keep_fees = forms.BooleanField(
        label=_("Keep payment, shipping and service fees"),
        required=False
    )
    cancel_allow_user_paid_keep_percentage = forms.DecimalField(
        label=_("Keep a percentual cancellation fee"),
        required=False
    )
    cancel_allow_user_paid_until = RelativeDateTimeField(
        label=_("Do not allow cancellations after"),
        required=False
    )


class PaymentSettingsForm(SettingsForm):
    payment_term_days = forms.IntegerField(
        label=_('Payment term in days'),
        help_text=_("The number of days after placing an order the user has to pay to preserve their reservation. If "
                    "you use slow payment methods like bank transfer, we recommend 14 days. If you only use real-time "
                    "payment methods, we recommend still setting two or three days to allow people to retry failed "
                    "payments."),
        validators=[MinValueValidator(0),
                    MaxValueValidator(1000000)]

    )
    payment_term_last = RelativeDateField(
        label=_('Last date of payments'),
        help_text=_("The last date any payments are accepted. This has precedence over the number of "
                    "days configured above. If you use the event series feature and an order contains tickets for "
                    "multiple dates, the earliest date will be used."),
        required=False,
    )
    payment_term_weekdays = forms.BooleanField(
        label=_('Only end payment terms on weekdays'),
        help_text=_("If this is activated and the payment term of any order ends on a Saturday or Sunday, it will be "
                    "moved to the next Monday instead. This is required in some countries by civil law. This will "
                    "not effect the last date of payments configured above."),
        required=False,
    )
    payment_term_expire_automatically = forms.BooleanField(
        label=_('Automatically expire unpaid orders'),
        help_text=_("If checked, all unpaid orders will automatically go from 'pending' to 'expired' "
                    "after the end of their payment deadline. This means that those tickets go back to "
                    "the pool and can be ordered by other people."),
        required=False
    )
    payment_term_accept_late = forms.BooleanField(
        label=_('Accept late payments'),
        help_text=_("Accept payments for orders even when they are in 'expired' state as long as enough "
                    "capacity is available. No payments will ever be accepted after the 'Last date of payments' "
                    "configured above."),
        required=False
    )
    tax_rate_default = forms.ModelChoiceField(
        queryset=TaxRule.objects.none(),
        label=_('Tax rule for payment fees'),
        required=False,
        help_text=_("The tax rule that applies for additional fees you configured for single payment methods. This "
                    "will set the tax rate and reverse charge rules, other settings of the tax rule are ignored.")
    )
    payment_explanation = I18nFormField(
        widget=I18nTextarea,
        widget_kwargs={'attrs': {
            'rows': 3,
        }},
        required=False,
        label=_("Guidance text"),
        help_text=_("This text will be shown above the payment options. You can explain the choices to the user here, "
                    "if you want.")
    )

    def clean(self):
        cleaned_data = super().clean()
        payment_term_last = cleaned_data.get('payment_term_last')
        if payment_term_last and self.obj.presale_end:
            if payment_term_last.date(self.obj) < self.obj.presale_end.date():
                self.add_error(
                    'payment_term_last',
                    _('The last payment date cannot be before the end of presale.'),
                )
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tax_rate_default'].queryset = self.obj.tax_rules.all()


class ProviderForm(SettingsForm):
    """
    This is a SettingsForm, but if fields are set to required=True, validation
    errors are only raised if the payment method is enabled.
    """

    def __init__(self, *args, **kwargs):
        self.settingspref = kwargs.pop('settingspref')
        self.provider = kwargs.pop('provider', None)
        super().__init__(*args, **kwargs)

    def prepare_fields(self):
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False
            if isinstance(v, I18nFormField):
                v._required = v.one_required
                v.one_required = False
                v.widget.enabled_locales = self.locales
            elif isinstance(v, (RelativeDateTimeField, RelativeDateField)):
                v.set_event(self.obj)

            if hasattr(v, '_as_type'):
                self.initial[k] = self.obj.settings.get(k, as_type=v._as_type, default=v.initial)

    def clean(self):
        cleaned_data = super().clean()
        enabled = cleaned_data.get(self.settingspref + '_enabled')
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))
        if self.provider:
            cleaned_data = self.provider.settings_form_clean(cleaned_data)
        return cleaned_data


class InvoiceSettingsForm(SettingsForm):
    allcountries = list(countries)
    allcountries.insert(0, ('', _('Select country')))

    invoice_address_asked = forms.BooleanField(
        label=_("Ask for invoice address"),
        required=False
    )
    invoice_address_required = forms.BooleanField(
        label=_("Require invoice address"),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
    )
    invoice_address_company_required = forms.BooleanField(
        label=_("Require a business addresses"),
        help_text=_('This will require users to enter a company name.'),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_required'}),
    )
    invoice_name_required = forms.BooleanField(
        label=_("Require customer name"),
        required=False,
    )
    invoice_address_vatid = forms.BooleanField(
        label=_("Ask for VAT ID"),
        help_text=_("Does only work if an invoice address is asked for. VAT ID is not required."),
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
        required=False
    )
    invoice_address_beneficiary = forms.BooleanField(
        label=_("Ask for beneficiary"),
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
        required=False
    )
    invoice_address_not_asked_free = forms.BooleanField(
        label=_('Do not ask for invoice address if an order is free'),
        required=False
    )
    invoice_include_free = forms.BooleanField(
        label=_("Show free products on invoices"),
        help_text=_("Note that invoices will never be generated for orders that contain only free "
                    "products."),
        required=False
    )
    invoice_address_explanation_text = I18nFormField(
        label=_("Invoice address explanation"),
        required=False,
        widget=I18nTextarea,
        widget_kwargs={'attrs': {'rows': '2'}},
        help_text=_("This text will be shown above the invoice address form during checkout.")
    )
    invoice_numbers_consecutive = forms.BooleanField(
        label=_("Generate invoices with consecutive numbers"),
        help_text=_("If deactivated, the order code will be used in the invoice number."),
        required=False
    )
    invoice_numbers_prefix = forms.CharField(
        label=_("Invoice number prefix"),
        help_text=_("This will be prepended to invoice numbers. If you leave this field empty, your event slug will "
                    "be used followed by a dash. Attention: If multiple events within the same organization use the "
                    "same value in this field, they will share their number range, i.e. every full number will be "
                    "used at most once over all of your events. This setting only affects future invoices. You can "
                    "use %Y (with century) %y (without century) to insert the year of the invoice, or %m and %d for "
                    "the day of month."),
        required=False,
    )
    invoice_numbers_prefix_cancellations = forms.CharField(
        label=_("Invoice number prefix for cancellations"),
        help_text=_("This will be prepended to invoice numbers of cancellations. If you leave this field empty, "
                    "the same numbering scheme will be used that you configured for regular invoices."),
        required=False,
    )
    invoice_generate = forms.ChoiceField(
        label=_("Generate invoices"),
        required=False,
        widget=forms.RadioSelect,
        choices=(
            ('False', _('Do not generate invoices')),
            ('admin', _('Only manually in admin panel')),
            ('user', _('Automatically on user request')),
            ('True', _('Automatically for all created orders')),
            ('paid', _('Automatically on payment')),
        ),
        help_text=_("Invoices will never be automatically generated for free orders.")
    )
    invoice_generate_sales_channels = forms.MultipleChoiceField(
        label=_('Generate invoices for Sales channels'),
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text=_("If you have enabled invoice generation in the previous setting, you can limit it here to specific "
                    "sales channels.")
    )
    invoice_attendee_name = forms.BooleanField(
        label=_("Show attendee names on invoices"),
        required=False
    )
    invoice_include_expire_date = forms.BooleanField(
        label=_("Show expiration date of order"),
        help_text=_("The expiration date will not be shown if the invoice is generated after the order is paid."),
        required=False
    )
    invoice_email_attachment = forms.BooleanField(
        label=_("Attach invoices to emails"),
        help_text=_("If invoices are automatically generated for all orders, they will be attached to the order "
                    "confirmation mail. If they are automatically generated on payment, they will be attached to the "
                    "payment confirmation mail. If they are not automatically generated, they will not be attached "
                    "to emails."),
        required=False
    )
    invoice_renderer = forms.ChoiceField(
        label=_("Invoice style"),
        required=True,
        choices=[]
    )
    invoice_address_from_name = forms.CharField(
        label=_("Company name"),
        required=False,
    )
    invoice_address_from = forms.CharField(
        label=_("Address line"),
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': _(
                'Albert Einstein Road 52'
            )
        }),
        required=False,
    )
    invoice_address_from_zipcode = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': '12345'
        }),
        required=False,
        label=_("ZIP code"),
    )
    invoice_address_from_city = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': _('Random City')
        }),
        required=False,
        label=_("City"),
    )
    invoice_address_from_country = forms.ChoiceField(
        choices=allcountries,
        required=False,
        label=_("Country"),
    )
    invoice_address_from_tax_id = forms.CharField(
        required=False,
        label=_("Domestic tax ID"),
    )
    invoice_address_from_vat_id = forms.CharField(
        required=False,
        label=_("EU VAT ID"),
    )
    invoice_introductory_text = I18nFormField(
        widget=I18nTextarea,
        widget_kwargs={'attrs': {
            'rows': 3,
            'placeholder': _(
                'e.g. With this document, we sent you the invoice for your ticket order.'
            )
        }},
        required=False,
        label=_("Introductory text"),
        help_text=_("Will be printed on every invoice above the invoice rows.")
    )
    invoice_additional_text = I18nFormField(
        widget=I18nTextarea,
        widget_kwargs={'attrs': {
            'rows': 3,
            'placeholder': _(
                'e.g. Thank you for your purchase! You can find more information on the event at ...'
            )
        }},
        required=False,
        label=_("Additional text"),
        help_text=_("Will be printed on every invoice below the invoice total.")
    )
    invoice_footer_text = I18nFormField(
        widget=I18nTextarea,
        widget_kwargs={'attrs': {
            'rows': 5,
            'placeholder': _(
                'e.g. your bank details, legal details like your VAT ID, registration numbers, etc.'
            )
        }},
        required=False,
        label=_("Footer"),
        help_text=_("Will be printed centered and in a smaller font at the end of every invoice page.")
    )
    invoice_language = forms.ChoiceField(
        widget=forms.Select, required=True,
        label=_("Invoice language"),
        choices=[('__user__', _('The user\'s language'))] + settings.LANGUAGES,
    )
    invoice_logo_image = ExtFileField(
        label=_('Logo image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        help_text=_('We will show your logo with a maximal height and width of 2.5 cm.')
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        self.fields['invoice_renderer'].choices = [
            (r.identifier, r.verbose_name) for r in event.get_invoice_renderers().values()
        ]
        self.fields['invoice_numbers_prefix'].widget.attrs['placeholder'] = event.slug.upper() + '-'
        if event.settings.invoice_numbers_prefix:
            self.fields['invoice_numbers_prefix_cancellations'].widget.attrs['placeholder'] = event.settings.invoice_numbers_prefix
        else:
            self.fields['invoice_numbers_prefix_cancellations'].widget.attrs['placeholder'] = event.slug.upper() + '-'
        locale_names = dict(settings.LANGUAGES)
        self.fields['invoice_language'].choices = [('__user__', _('The user\'s language'))] + [(a, locale_names[a]) for a in event.settings.locales]
        self.fields['invoice_generate_sales_channels'].choices = (
            (c.identifier, c.verbose_name) for c in get_all_sales_channels().values()
        )


def multimail_validate(val):
    s = val.split(',')
    for part in s:
        validate_email(part.strip())
    return s


class MailSettingsForm(SettingsForm):
    mail_prefix = forms.CharField(
        label=_("Subject prefix"),
        help_text=_("This will be prepended to the subject of all outgoing emails, formatted as [prefix]. "
                    "Choose, for example, a short form of your event name."),
        required=False
    )
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing emails"),
    )
    mail_from_name = forms.CharField(
        label=_("Sender name"),
        help_text=_("Sender name used in conjunction with the sender address for outgoing emails. "
                    "Defaults to your event name."),
        required=False
    )
    mail_bcc = forms.CharField(
        label=_("Bcc address"),
        help_text=_("All emails will be sent to this address as a Bcc copy"),
        validators=[multimail_validate],
        required=False,
        max_length=255
    )
    mail_attach_ical = forms.BooleanField(
        label=_("Attach calendar files"),
        help_text=_("If enabled, we will attach an .ics calendar file to order confirmation emails."),
        required=False
    )

    mail_text_signature = I18nFormField(
        label=_("Signature"),
        required=False,
        widget=I18nTextarea,
        help_text=_("This will be attached to every email. Available placeholders: {event}"),
        validators=[PlaceholderValidator(['{event}'])],
        widget_kwargs={'attrs': {
            'rows': '4',
            'placeholder': _(
                'e.g. your contact details'
            )
        }}
    )
    mail_html_renderer = forms.ChoiceField(
        label=_("HTML mail renderer"),
        required=True,
        choices=[]
    )

    mail_text_order_placed = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nTextarea,
    )
    mail_send_order_placed_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_text_order_placed_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nTextarea,
    )

    mail_text_order_paid = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nTextarea,
    )
    mail_send_order_paid_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_text_order_paid_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nTextarea,
    )

    mail_text_order_free = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nTextarea,
    )
    mail_send_order_free_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_text_order_free_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nTextarea,
    )

    mail_text_order_changed = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_resend_link = I18nFormField(
        label=_("Text (sent by admin)"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_resend_all_links = I18nFormField(
        label=_("Text (requested by user)"),
        required=False,
        widget=I18nTextarea,
    )
    mail_days_order_expire_warning = forms.IntegerField(
        label=_("Number of days"),
        required=True,
        min_value=0,
        help_text=_("This email will be sent out this many days before the order expires. If the "
                    "value is 0, the mail will never be sent.")
    )
    mail_text_order_expire_warning = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_waiting_list = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_order_canceled = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_order_custom_mail = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_download_reminder = I18nFormField(
        label=_("Text sent to order contact address"),
        required=False,
        widget=I18nTextarea,
    )
    mail_send_download_reminder_attendee = forms.BooleanField(
        label=_("Send an email to attendees"),
        help_text=_('If the order contains attendees with email addresses different from the person who orders the '
                    'tickets, the following email will be sent out to the attendees.'),
        required=False,
    )
    mail_text_download_reminder_attendee = I18nFormField(
        label=_("Text sent to attendees"),
        required=False,
        widget=I18nTextarea,
    )
    mail_days_download_reminder = forms.IntegerField(
        label=_("Number of days"),
        required=False,
        min_value=0,
        help_text=_("This email will be sent out this many days before the order event starts. If the "
                    "field is empty, the mail will never be sent.")
    )
    mail_text_order_placed_require_approval = I18nFormField(
        label=_("Received order"),
        required=False,
        widget=I18nTextarea,
    )
    mail_text_order_approved = I18nFormField(
        label=_("Approved order"),
        required=False,
        widget=I18nTextarea,
        help_text=_("This will only be sent out for non-free orders. Free orders will receive the free order "
                    "template from above instead."),
    )
    mail_text_order_denied = I18nFormField(
        label=_("Denied order"),
        required=False,
        widget=I18nTextarea,
    )
    smtp_use_custom = forms.BooleanField(
        label=_("Use custom SMTP server"),
        help_text=_("All mail related to your event will be sent over the smtp server specified by you."),
        required=False
    )
    smtp_host = forms.CharField(
        label=_("Hostname"),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'mail.example.org'})
    )
    smtp_port = forms.IntegerField(
        label=_("Port"),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 587, 465, 25, ...'})
    )
    smtp_username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(attrs={'placeholder': 'myuser@example.org'}),
        required=False
    )
    smtp_password = forms.CharField(
        label=_("Password"),
        required=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password'  # see https://bugs.chromium.org/p/chromium/issues/detail?id=370363#c7
        }),
    )
    smtp_use_tls = forms.BooleanField(
        label=_("Use STARTTLS"),
        help_text=_("Commonly enabled on port 587."),
        required=False
    )
    smtp_use_ssl = forms.BooleanField(
        label=_("Use SSL"),
        help_text=_("Commonly enabled on port 465."),
        required=False
    )
    base_context = {
        'mail_text_order_placed': ['event', 'order', 'payment'],
        'mail_text_order_placed_attendee': ['event', 'order', 'position'],
        'mail_text_order_placed_require_approval': ['event', 'order'],
        'mail_text_order_approved': ['event', 'order'],
        'mail_text_order_denied': ['event', 'order', 'comment'],
        'mail_text_order_paid': ['event', 'order', 'payment_info'],
        'mail_text_order_paid_attendee': ['event', 'order', 'position'],
        'mail_text_order_free': ['event', 'order'],
        'mail_text_order_free_attendee': ['event', 'order', 'position'],
        'mail_text_order_changed': ['event', 'order'],
        'mail_text_order_canceled': ['event', 'order'],
        'mail_text_order_expire_warning': ['event', 'order'],
        'mail_text_order_custom_mail': ['event', 'order'],
        'mail_text_download_reminder': ['event', 'order'],
        'mail_text_download_reminder_attendee': ['event', 'order', 'position'],
        'mail_text_resend_link': ['event', 'order'],
        'mail_text_waiting_list': ['event', 'waiting_list_entry'],
        'mail_text_resend_all_links': ['event', 'orders']
    }

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    def __init__(self, *args, **kwargs):
        self.event = event = kwargs.get('obj')
        super().__init__(*args, **kwargs)
        self.fields['mail_html_renderer'].choices = [
            (r.identifier, r.verbose_name) for r in event.get_html_mail_renderers().values()
        ]
        for k, v in self.base_context.items():
            self._set_field_placeholders(k, v)

        for k, v in list(self.fields.items()):
            if k.endswith('_attendee') and not event.settings.attendee_emails_asked:
                # If we don't ask for attendee emails, we can't send them anything and we don't need to clutter
                # the user interface with it
                del self.fields[k]

    def clean(self):
        data = self.cleaned_data
        if not data.get('smtp_password') and data.get('smtp_username'):
            # Leave password unchanged if the username is set and the password field is empty.
            # This makes it impossible to set an empty password as long as a username is set, but
            # Python's smtplib does not support password-less schemes anyway.
            data['smtp_password'] = self.initial.get('smtp_password')

        if data.get('smtp_use_tls') and data.get('smtp_use_ssl'):
            raise ValidationError(_('You can activate either SSL or STARTTLS security, but not both at the same time.'))


class TicketSettingsForm(SettingsForm):
    ticket_download = forms.BooleanField(
        label=_("Use feature"),
        help_text=_("Use pretix to generate tickets for the user to download and print out."),
        required=False
    )
    ticket_download_date = RelativeDateTimeField(
        label=_("Download date"),
        help_text=_("Ticket download will be offered after this date. If you use the event series feature and an order "
                    "contains tickets for multiple event dates, download of all tickets will be available if at least "
                    "one of the event dates allows it."),
        required=False,
    )
    ticket_download_addons = forms.BooleanField(
        label=_("Offer to download tickets separately for add-on products"),
        required=False,
    )
    ticket_download_nonadm = forms.BooleanField(
        label=_("Generate tickets for non-admission products"),
        required=False,
    )
    ticket_download_pending = forms.BooleanField(
        label=_("Offer to download tickets even before an order is paid"),
        required=False,
    )

    def prepare_fields(self):
        # See clean()
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False
            if isinstance(v, I18nFormField):
                v._required = v.one_required
                v.one_required = False
                v.widget.enabled_locales = self.locales

    def clean(self):
        # required=True files should only be required if the feature is enabled
        cleaned_data = super().clean()
        enabled = cleaned_data.get('ticket_download') == 'True'
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and (val is None or val == ""):
                self.add_error(k, _('This field is required.'))


class CommentForm(I18nModelForm):
    class Meta:
        model = Event
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'helper-width-100',
            }),
        }


class CountriesAndEU(Countries):
    override = {
        'ZZ': _('Any country'),
        'EU': _('European Union')
    }
    first = ['ZZ', 'EU']


class TaxRuleLineForm(forms.Form):
    country = LazyTypedChoiceField(
        choices=CountriesAndEU(),
        required=False
    )
    address_type = forms.ChoiceField(
        choices=[
            ('', _('Any customer')),
            ('individual', _('Individual')),
            ('business', _('Business')),
            ('business_vat_id', _('Business with valid VAT ID')),
        ],
        required=False
    )
    action = forms.ChoiceField(
        choices=[
            ('vat', _('Charge VAT')),
            ('reverse', _('Reverse charge')),
            ('no', _('No VAT')),
        ],
    )


TaxRuleLineFormSet = formset_factory(
    TaxRuleLineForm,
    can_order=False, can_delete=True, extra=0
)


class TaxRuleForm(I18nModelForm):
    class Meta:
        model = TaxRule
        fields = ['name', 'rate', 'price_includes_tax', 'eu_reverse_charge', 'home_country']


class WidgetCodeForm(forms.Form):
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', "Date"),
        required=False,
        queryset=SubEvent.objects.none()
    )
    language = forms.ChoiceField(
        label=_("Language"),
        required=True,
        choices=settings.LANGUAGES
    )
    voucher = forms.CharField(
        label=_("Pre-selected voucher"),
        required=False,
        help_text=_("If set, the widget will show products as if this voucher has been entered and when a product is "
                    "bought via the widget, this voucher will be used. This can for example be used to provide "
                    "widgets that give discounts or unlock secret products.")
    )
    compatibility_mode = forms.BooleanField(
        label=_("Compatibility mode"),
        required=False,
        help_text=_("Our regular widget doesn't work in all website builders. If you run into trouble, try using "
                    "this compatibility mode.")
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
        else:
            del self.fields['subevent']

        self.fields['language'].choices = [(l, n) for l, n in settings.LANGUAGES if l in self.event.settings.locales]

    def clean_voucher(self):
        v = self.cleaned_data.get('voucher')
        if not v:
            return

        if not self.event.vouchers.filter(code=v).exists():
            raise ValidationError(_('The given voucher code does not exist.'))

        return v


class EventDeleteForm(forms.Form):
    error_messages = {
        'slug_wrong': _("The slug you entered was not correct."),
    }
    slug = forms.CharField(
        max_length=255,
        label=_("Event slug"),
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if slug != self.event.slug:
            raise forms.ValidationError(
                self.error_messages['slug_wrong'],
                code='slug_wrong',
            )
        return slug


class QuickSetupForm(I18nForm):
    show_quota_left = forms.BooleanField(
        label=_("Show number of tickets left"),
        help_text=_("Publicly show how many tickets of a certain type are still available."),
        required=False
    )
    waiting_list_enabled = forms.BooleanField(
        label=_("Waiting list"),
        help_text=_("Once a ticket is sold out, people can add themselves to a waiting list. As soon as a ticket "
                    "becomes available again, it will be reserved for the first person on the waiting list and this "
                    "person will receive an email notification with a voucher that can be used to buy a ticket."),
        required=False
    )
    ticket_download = forms.BooleanField(
        label=_("Ticket downloads"),
        help_text=_("Your customers will be able to download their tickets in PDF format."),
        required=False
    )
    attendee_names_required = forms.BooleanField(
        label=_("Require all attendees to fill in their names"),
        help_text=_("By default, we will ask for names but not require them. You can turn this off completely in the "
                    "settings."),
        required=False
    )
    imprint_url = forms.URLField(
        label=_("Imprint URL"),
        help_text=_("This should point e.g. to a part of your website that has your contact details and legal "
                    "information."),
        required=False,
    )
    contact_mail = forms.EmailField(
        label=_("Contact address"),
        required=False,
        help_text=_("We'll show this publicly to allow attendees to contact you.")
    )
    total_quota = forms.IntegerField(
        label=_("Total capacity"),
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                'placeholder': '∞'
            }
        ),
        required=False
    )
    payment_stripe__enabled = forms.BooleanField(
        label=_("Payment via Stripe"),
        help_text=_("Stripe is an online payments processor supporting credit cards and lots of other payment options. "
                    "To accept payments via Stripe, you will need to set up an account with them, which takes less "
                    "than five minutes using their simple interface."),
        required=False
    )
    payment_banktransfer__enabled = forms.BooleanField(
        label=_("Payment by bank transfer"),
        help_text=_("Your customers will be instructed to wire the money to your account. You can then import your "
                    "bank statements to process the payments within pretix, or mark them as paid manually."),
        required=False
    )
    btf = BankTransfer.form_fields()
    payment_banktransfer_bank_details_type = btf['bank_details_type']
    payment_banktransfer_bank_details_sepa_name = btf['bank_details_sepa_name']
    payment_banktransfer_bank_details_sepa_iban = btf['bank_details_sepa_iban']
    payment_banktransfer_bank_details_sepa_bic = btf['bank_details_sepa_bic']
    payment_banktransfer_bank_details_sepa_bank = btf['bank_details_sepa_bank']
    payment_banktransfer_bank_details = btf['bank_details']

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop('event', None)
        self.locales = self.obj.settings.get('locales') if self.obj else kwargs.pop('locales', None)
        kwargs['locales'] = self.locales
        super().__init__(*args, **kwargs)
        if not self.obj.settings.payment_stripe_connect_client_id:
            del self.fields['payment_stripe__enabled']
        self.fields['payment_banktransfer_bank_details'].required = False
        for f in self.fields.values():
            if 'data-required-if' in f.widget.attrs:
                del f.widget.attrs['data-required-if']

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('payment_banktransfer__enabled'):
            provider = BankTransfer(self.obj)
            cleaned_data = provider.settings_form_clean(cleaned_data)
        return cleaned_data


class QuickSetupProductForm(I18nForm):
    name = I18nFormField(
        max_length=255,
        label=_("Product name"),
        widget=I18nTextInput
    )
    default_price = forms.DecimalField(
        label=_("Price (optional)"),
        max_digits=7, decimal_places=2, required=False,
        localize=True,
        widget=forms.TextInput(
            attrs={
                'placeholder': _('Free')
            }
        ),
    )
    quota = forms.IntegerField(
        label=_("Quantity available"),
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                'placeholder': '∞'
            }
        ),
        initial=100,
        required=False
    )


class BaseQuickSetupProductFormSet(I18nFormSetMixin, forms.BaseFormSet):

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


QuickSetupProductFormSet = formset_factory(
    QuickSetupProductForm,
    formset=BaseQuickSetupProductFormSet,
    can_order=False, can_delete=True, extra=0
)
