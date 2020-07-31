from urllib.parse import urlencode, urlparse

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, validate_email
from django.db.models import Q
from django.forms import formset_factory
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.timezone import get_current_timezone_name
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from django_countries import Countries
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
from pretix.multidomain.models import KnownDomain
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
            del self.fields['date_to']

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
        ).exists() or user.is_staff


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
        self.domain = kwargs.pop('domain', False)

        kwargs.setdefault('initial', {})
        self.instance = kwargs['instance']
        if self.domain and self.instance:
            initial_domain = self.instance.domains.first()
            if initial_domain:
                kwargs['initial'].setdefault('domain', initial_domain.domainname)

        super().__init__(*args, **kwargs)
        if not self.change_slug:
            self.fields['slug'].widget.attrs['readonly'] = 'readonly'
        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['location'].widget.attrs['placeholder'] = _(
            'Sample Conference Center\nHeidelberg, Germany'
        )
        if self.domain:
            self.fields['domain'] = forms.CharField(
                max_length=255,
                label=_('Custom domain'),
                required=False,
                help_text=_('You need to configure the custom domain in the webserver beforehand.')
            )

    def clean_domain(self):
        d = self.cleaned_data['domain']
        if d:
            if d == urlparse(settings.SITE_URL).hostname:
                raise ValidationError(
                    _('You cannot choose the base domain of this installation.')
                )
            if KnownDomain.objects.filter(domainname=d).exclude(event=self.instance.pk).exists():
                raise ValidationError(
                    _('This domain is already in use for a different event or organizer.')
                )
        return d

    def save(self, commit=True):
        instance = super().save(commit)

        if self.domain:
            current_domain = instance.domains.first()
            if self.cleaned_data['domain']:
                if current_domain and current_domain.domainname != self.cleaned_data['domain']:
                    current_domain.delete()
                    KnownDomain.objects.create(
                        organizer=instance.organizer, event=instance, domainname=self.cleaned_data['domain']
                    )
                elif not current_domain:
                    KnownDomain.objects.create(
                        organizer=instance.organizer, event=instance, domainname=self.cleaned_data['domain']
                    )
            elif current_domain:
                current_domain.delete()
            instance.cache.clear()

        return instance

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
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Event timezone"),
    )
    name_scheme = forms.ChoiceField(
        label=_("Name format"),
        help_text=_("This defines how pretix will ask for human names. Changing this after you already received "
                    "orders might lead to unexpected behavior when sorting or changing names."),
        required=True,
    )
    name_scheme_titles = forms.ChoiceField(
        label=_("Allowed titles"),
        help_text=_("If the naming scheme you defined above allows users to input a title, you can use this to "
                    "restrict the set of selectable titles."),
        required=False,
    )
    logo_image = ExtFileField(
        label=_('Header image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        max_size=10 * 1024 * 1024,
        help_text=_('If you provide a logo image, we will by default not show your event name and date '
                    'in the page header. By default, we show your logo with a size of up to 1140x120 pixels. You '
                    'can increase the size with the setting below. We recommend not using small details on the picture '
                    'as it will be resized on smaller screens.')
    )
    logo_image_large = forms.BooleanField(
        label=_('Use header image in its full size'),
        help_text=_('We recommend to upload a picture at least 1170 pixels wide.'),
        required=False,
    )
    logo_show_title = forms.BooleanField(
        label=_('Show event title even if a header image is present'),
        help_text=_('The title will only be shown on the event front page.'),
        required=False,
    )
    og_image = ExtFileField(
        label=_('Social media image'),
        ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
        required=False,
        max_size=10 * 1024 * 1024,
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
    theme_color_background = forms.CharField(
        label=_("Page background color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),

        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield no-contrast'})
    )
    theme_round_borders = forms.BooleanField(
        label=_("Use round edges"),
        required=False,
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
        'show_dates_on_frontpage',
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
        'event_list_type',
        'frontpage_text',
        'attendee_names_asked',
        'attendee_names_required',
        'attendee_emails_asked',
        'attendee_emails_required',
        'attendee_company_asked',
        'attendee_company_required',
        'attendee_addresses_asked',
        'attendee_addresses_required',
        'banner_text',
        'banner_text_bottom',
        'order_email_asked_twice',
        'last_order_modification_date',
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
            del self.fields['event_list_type']
        self.fields['primary_font'].choices += [
            (a, {"title": a, "data": v}) for a, v in get_fonts().items()
        ]


class CancelSettingsForm(SettingsForm):
    auto_fields = [
        'cancel_allow_user',
        'cancel_allow_user_until',
        'cancel_allow_user_paid',
        'cancel_allow_user_paid_until',
        'cancel_allow_user_paid_keep',
        'cancel_allow_user_paid_keep_fees',
        'cancel_allow_user_paid_keep_percentage',
        'cancel_allow_user_paid_adjust_fees',
        'cancel_allow_user_paid_adjust_fees_explanation',
        'cancel_allow_user_paid_refund_as_giftcard',
        'cancel_allow_user_paid_require_approval',
        'change_allow_user_variation',
        'change_allow_user_price',
        'change_allow_user_until',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.obj.settings.giftcard_expiry_years is not None:
            self.fields['cancel_allow_user_paid_refund_as_giftcard'].help_text = gettext(
                'You have configured gift cards to be valid {} years plus the year the gift card is issued in.'
            ).format(self.obj.settings.giftcard_expiry_years)


class PaymentSettingsForm(SettingsForm):
    auto_fields = [
        'payment_term_days',
        'payment_term_last',
        'payment_term_weekdays',
        'payment_term_expire_automatically',
        'payment_term_accept_late',
        'payment_explanation',
    ]
    tax_rate_default = forms.ModelChoiceField(
        queryset=TaxRule.objects.none(),
        label=_('Tax rule for payment fees'),
        required=False,
        help_text=_("The tax rule that applies for additional fees you configured for single payment methods. This "
                    "will set the tax rate and reverse charge rules, other settings of the tax rule are ignored.")
    )

    def clean(self):
        data = super().clean()
        settings_dict = self.obj.settings.freeze()
        settings_dict.update(data)
        validate_settings(self.obj, data)
        return data

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

    auto_fields = [
        'invoice_address_asked',
        'invoice_address_required',
        'invoice_address_vatid',
        'invoice_address_company_required',
        'invoice_address_beneficiary',
        'invoice_address_custom_field',
        'invoice_name_required',
        'invoice_address_not_asked_free',
        'invoice_include_free',
        'invoice_show_payments',
        'invoice_reissue_after_modify',
        'invoice_generate',
        'invoice_attendee_name',
        'invoice_include_expire_date',
        'invoice_numbers_consecutive',
        'invoice_numbers_prefix',
        'invoice_numbers_prefix_cancellations',
        'invoice_numbers_counter_length',
        'invoice_address_explanation_text',
        'invoice_email_attachment',
        'invoice_address_from_name',
        'invoice_address_from',
        'invoice_address_from_zipcode',
        'invoice_address_from_city',
        'invoice_address_from_country',
        'invoice_address_from_tax_id',
        'invoice_address_from_vat_id',
        'invoice_introductory_text',
        'invoice_additional_text',
        'invoice_footer_text',
        'invoice_eu_currencies',
    ]

    invoice_generate_sales_channels = forms.MultipleChoiceField(
        label=_('Generate invoices for Sales channels'),
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text=_("If you have enabled invoice generation in the previous setting, you can limit it here to specific "
                    "sales channels.")
    )
    invoice_renderer = forms.ChoiceField(
        label=_("Invoice style"),
        required=True,
        choices=[]
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
        max_size=10 * 1024 * 1024,
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

    def clean(self):
        data = super().clean()
        settings_dict = self.obj.settings.freeze()
        settings_dict.update(data)
        validate_settings(self.obj, data)
        return data


def multimail_validate(val):
    s = val.split(',')
    for part in s:
        validate_email(part.strip())
    return s


def contains_web_channel_validate(val):
    if "web" not in val:
        raise ValidationError(_("The online shop must be selected to receive these emails."))


class MailSettingsForm(SettingsForm):
    auto_fields = [
        'mail_prefix',
        'mail_from',
        'mail_from_name',
        'mail_attach_ical',
    ]

    mail_sales_channel_placed_paid = forms.MultipleChoiceField(
        choices=lambda: [(ident, sc.verbose_name) for ident, sc in get_all_sales_channels().items()],
        label=_('Sales channels for checkout emails'),
        help_text=_('The order placed and paid emails will only be send to orders from these sales channels. '
                    'The online shop must be enabled.'),
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        validators=[contains_web_channel_validate],
    )

    mail_sales_channel_download_reminder = forms.MultipleChoiceField(
        choices=lambda: [(ident, sc.verbose_name) for ident, sc in get_all_sales_channels().items()],
        label=_('Sales channels'),
        help_text=_('This email will only be send to orders from these sales channels. The online shop must be enabled.'),
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'scrolling-multiple-choice'}
        ),
        validators=[contains_web_channel_validate],
    )

    mail_bcc = forms.CharField(
        label=_("Bcc address"),
        help_text=_("All emails will be sent to this address as a Bcc copy"),
        validators=[multimail_validate],
        required=False,
        max_length=255
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
    auto_fields = [
        'ticket_download',
        'ticket_download_date',
        'ticket_download_addons',
        'ticket_download_nonadm',
        'ticket_download_pending',
    ]

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
    rate = forms.DecimalField(
        label=_('Deviating tax rate'),
        max_digits=10, decimal_places=2,
        required=False
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
        max_length=200,  # Max length of Quota.name
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


class ItemMetaPropertyForm(forms.ModelForm):
    class Meta:
        fields = ['name', 'default']
        widgets = {
            'default': forms.TextInput()
        }


class ConfirmTextForm(I18nForm):
    text = I18nFormField(
        widget=I18nTextarea,
        widget_kwargs={'attrs': {'rows': '2'}},
    )


class BaseConfirmTextFormSet(I18nFormSetMixin, forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


ConfirmTextFormset = formset_factory(
    ConfirmTextForm,
    formset=BaseConfirmTextFormSet,
    can_order=True, can_delete=True, extra=0
)
