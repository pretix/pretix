from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q
from django.utils.timezone import get_current_timezone_name
from django.utils.translation import ugettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea
from pytz import common_timezones, timezone

from pretix.base.forms import I18nModelForm, PlaceholderValidator, SettingsForm
from pretix.base.models import Event, Organizer
from pretix.base.reldate import RelativeDateField, RelativeDateTimeField
from pretix.control.forms import ExtFileField, SlugWidget
from pretix.multidomain.urlreverse import build_absolute_uri


class EventWizardFoundationForm(forms.Form):
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        label=_("Use languages"),
        widget=forms.CheckboxSelectMultiple,
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
        super().__init__(*args, **kwargs)
        self.fields['organizer'] = forms.ModelChoiceField(
            label=_("Organizer"),
            queryset=Organizer.objects.filter(
                id__in=self.user.teams.filter(can_create_events=True).values_list('organizer', flat=True)
            ),
            widget=forms.RadioSelect,
            empty_label=None,
            required=True
        )


class EventWizardBasicsForm(I18nModelForm):
    error_messages = {
        'duplicate_slug': _("You already used this slug for a different event. Please choose a new one."),
    }
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
    )
    locale = forms.ChoiceField(
        choices=settings.LANGUAGES,
        label=_("Default language"),
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
        ]
        widgets = {
            'date_from': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'date_to': forms.DateTimeInput(attrs={'class': 'datetimepicker',
                                                  'data-date-after': '#id_basics-date_from'}),
            'presale_start': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'presale_end': forms.DateTimeInput(attrs={'class': 'datetimepicker',
                                                      'data-date-after': '#id_basics-presale_start'}),
            'slug': SlugWidget
        }

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.locales = kwargs.get('locales')
        self.has_subevents = kwargs.pop('has_subevents')
        kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.initial['timezone'] = get_current_timezone_name()
        self.fields['locale'].choices = [(a, b) for a, b in settings.LANGUAGES if a in self.locales]
        self.fields['location'].widget.attrs['rows'] = '3'
        self.fields['slug'].widget.prefix = build_absolute_uri(self.organizer, 'presale:organizer.index')
        if self.has_subevents:
            del self.fields['presale_start']
            del self.fields['presale_end']

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
        if Event.objects.filter(slug=slug, organizer=self.organizer).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug'
            )
        return slug


class EventWizardCopyForm(forms.Form):

    @staticmethod
    def copy_from_queryset(user):
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
        kwargs.pop('has_subevents')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['copy_from_event'] = forms.ModelChoiceField(
            label=_("Copy configuration from"),
            queryset=EventWizardCopyForm.copy_from_queryset(self.user),
            widget=forms.RadioSelect,
            empty_label=_('Do not copy'),
            required=False
        )


class EventUpdateForm(I18nModelForm):
    def clean_slug(self):
        return self.instance.slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].widget.attrs['readonly'] = 'readonly'
        self.fields['location'].widget.attrs['rows'] = '3'

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
        ]
        widgets = {
            'date_from': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'date_to': forms.DateTimeInput(attrs={'class': 'datetimepicker', 'data-date-after': '#id_date_from'}),
            'date_admission': forms.DateTimeInput(attrs={'class': 'datetimepicker',
                                                         'data-date-default': '#id_date_from'}),
            'presale_start': forms.DateTimeInput(attrs={'class': 'datetimepicker'}),
            'presale_end': forms.DateTimeInput(attrs={'class': 'datetimepicker',
                                                      'data-date-after': '#id_presale_start'}),
        }


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
    show_items_outside_presale_period = forms.BooleanField(
        label=_("Show items outside presale period"),
        help_text=_("Show item details before presale has started and after presale has ended"),
        required=False
    )
    display_net_prices = forms.BooleanField(
        label=_("Show net prices instead of gross prices in the product list (not recommended!)"),
        help_text=_("Independent of your choice, the cart will show gross prices as this the price that needs to be "
                    "paid"),
        required=False
    )
    presale_start_show_date = forms.BooleanField(
        label=_("Show start date"),
        help_text=_("Show the presale start date before presale has started."),
        widget=forms.CheckboxInput,
        required=False
    )
    last_order_modification_date = RelativeDateTimeField(
        label=_('Last date of modifications'),
        help_text=_("The last date users can modify details of their orders, such as attendee names or "
                    "answers to questions. If you use the event series feature and an order contains tickest for "
                    "multiple event dates, the earliest date will be used."),
        required=False,
    )
    timezone = forms.ChoiceField(
        choices=((a, a) for a in common_timezones),
        label=_("Default timezone"),
    )
    locales = forms.MultipleChoiceField(
        choices=settings.LANGUAGES,
        widget=forms.CheckboxSelectMultiple,
        label=_("Available languages"),
    )
    locale = forms.ChoiceField(
        choices=settings.LANGUAGES,
        label=_("Default language"),
    )
    show_quota_left = forms.BooleanField(
        label=_("Show number of tickets left"),
        help_text=_("Publicly show how many tickets of a certain type are still available."),
        required=False
    )
    waiting_list_enabled = forms.BooleanField(
        label=_("Enable waiting list"),
        help_text=_("Once a ticket is sold out, people can add themselves to a waiting list. As soon as a ticket "
                    "becomes available again, it will be reserved for the first person on the waiting list and this "
                    "person will receive an email notification with a voucher that can be used to buy a ticket."),
        required=False
    )
    waiting_list_hours = forms.IntegerField(
        label=_("Waiting list response time"),
        min_value=6,
        help_text=_("If a ticket voucher is sent to a person on the waiting list, it has to be redeemed within this "
                    "number of hours until it expires and can be re-assigned to the next person on the list."),
        required=False,
        widget=forms.NumberInput(attrs={'data-display-dependency': '#id_settings-waiting_list_enabled'}),
    )
    waiting_list_auto = forms.BooleanField(
        label=_("Automatic waiting list assignments"),
        help_text=_("If ticket capacity becomes free, automatically create a voucher and send it to the first person "
                    "on the waiting list for that product. If this is not active, mails will not be send automatically "
                    "but you can send them manually via the control panel."),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_settings-waiting_list_enabled'}),
    )
    attendee_names_asked = forms.BooleanField(
        label=_("Ask for attendee names"),
        help_text=_("Ask for a name for all tickets which include admission to the event."),
        required=False,
    )
    attendee_names_required = forms.BooleanField(
        label=_("Require attendee names"),
        help_text=_("Require customers to fill in the names of all attendees."),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_names_asked'}),
    )
    attendee_emails_asked = forms.BooleanField(
        label=_("Ask for email addresses per ticket"),
        help_text=_("Normally, pretix asks for one email address per order and the order confirmation will be sent "
                    "only to that email address. If you enable this option, the system will additionally ask for "
                    "individual email addresses for every admission ticket. This might be useful if you want to "
                    "obtain individual addresses for every attendee even in case of group orders. However, "
                    "pretix will send the order confirmation only to the one primary email address, not to the "
                    "per-attendee addresses."),
        required=False
    )
    attendee_emails_required = forms.BooleanField(
        label=_("Require email addresses per ticket"),
        help_text=_("Require customers to fill in individual e-mail addresses for all admission tickets. See the "
                    "above option for more details. One email address for the order confirmation will always be "
                    "required regardless of this setting."),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_emails_asked'}),
    )
    order_email_asked_twice = forms.BooleanField(
        label=_("Ask for the order email address twice"),
        help_text=_("Require customers to fill in the primary email address twice to avoid errors."),
        required=False,
    )
    max_items_per_order = forms.IntegerField(
        min_value=1,
        label=_("Maximum number of items per order"),
        help_text=_("Add-on products will not be counted.")
    )
    reservation_time = forms.IntegerField(
        min_value=0,
        label=_("Reservation period"),
        help_text=_("The number of minutes the items in a user's cart are reserved for this user."),
    )
    imprint_url = forms.URLField(
        label=_("Imprint URL"),
        required=False,
    )
    contact_mail = forms.EmailField(
        label=_("Contact address"),
        required=False,
        help_text=_("Public email address for contacting the organizer")
    )
    cancel_allow_user = forms.BooleanField(
        label=_("Allow users to cancel unpaid orders"),
        help_text=_("If checked, users can cancel orders by themselves as long as they are not yet paid."),
        required=False
    )

    def clean(self):
        data = super().clean()
        if data['locale'] not in data['locales']:
            raise ValidationError({
                'locale': _('Your default locale must also be enabled for your event (see box above).')
            })
        if data['attendee_names_required'] and not data['attendee_names_asked']:
            raise ValidationError({
                'attendee_names_required': _('You cannot require specifying attendee names if you do not ask for them.')
            })
        if data['attendee_emails_required'] and not data['attendee_emails_asked']:
            raise ValidationError({
                'attendee_emails_required': _('You have to ask for attendee emails if you want to make them required.')
            })
        return data


class PaymentSettingsForm(SettingsForm):
    payment_term_days = forms.IntegerField(
        label=_('Payment term in days'),
        help_text=_("The number of days after placing an order the user has to pay to preserve his reservation."),
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
        help_text=_("If this is activated and the payment term of any order ends on a saturday or sunday, it will be "
                    "moved to the next monday instead. This is required in some countries by civil law. This will "
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
    tax_rate_default = forms.DecimalField(
        label=_('Tax rate for payment fees'),
        help_text=_("The tax rate that applies for additional fees you configured for single payment methods "
                    "(in percent)."),
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


class ProviderForm(SettingsForm):
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
            if isinstance(v, I18nFormField):
                v._required = v.one_required
                v.one_required = False
                v.widget.enabled_locales = self.locales
            elif isinstance(v, (RelativeDateTimeField, RelativeDateField)):
                v.set_event(self.obj)

    def clean(self):
        cleaned_data = super().clean()
        enabled = cleaned_data.get(self.settingspref + '_enabled')
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and not val:
                self.add_error(k, _('This field is required.'))


class InvoiceSettingsForm(SettingsForm):
    invoice_address_asked = forms.BooleanField(
        label=_("Ask for invoice address"),
        required=False
    )
    invoice_address_required = forms.BooleanField(
        label=_("Require invoice address"),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
    )
    invoice_name_required = forms.BooleanField(
        label=_("Require customer name"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={'data-checkbox-dependency': '#id_invoice_address_asked',
                   'data-inverse-dependency': '#id_invoice_address_required'}
        ),
    )
    invoice_address_vatid = forms.BooleanField(
        label=_("Ask for VAT ID"),
        help_text=_("Does only work if an invoice address is asked for. VAT ID is not required."),
        widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
        required=False
    )
    invoice_include_free = forms.BooleanField(
        label=_("Show free products on invoices"),
        help_text=_("Note that invoices will never be generated for orders that contain only free "
                    "products."),
        required=False
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
                    "used at most once over all of your events. This setting only affects future invoices."),
        required=False,
    )
    invoice_generate = forms.ChoiceField(
        label=_("Generate invoices"),
        required=False,
        choices=(
            ('False', _('No')),
            ('admin', _('Manually in admin panel')),
            ('user', _('Automatically on user request')),
            ('True', _('Automatically for all created orders')),
            ('paid', _('Automatically on payment')),
        )
    )
    invoice_renderer = forms.ChoiceField(
        label=_("Invoice style"),
        required=True,
        choices=[]
    )
    invoice_address_from = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5}), required=False,
        label=_("Your address"),
        help_text=_("Will be printed as the sender on invoices. Be sure to include relevant details required in "
                    "your jurisdiction (e.g. your VAT ID).")
    )
    invoice_introductory_text = I18nFormField(
        widget=I18nTextarea,
        required=False,
        label=_("Introductory text"),
        help_text=_("Will be printed on every invoice above the invoice rows.")
    )
    invoice_additional_text = I18nFormField(
        widget=I18nTextarea,
        required=False,
        label=_("Additional text"),
        help_text=_("Will be printed on every invoice below the invoice total.")
    )
    invoice_footer_text = I18nFormField(
        widget=I18nTextarea,
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


class MailSettingsForm(SettingsForm):
    mail_prefix = forms.CharField(
        label=_("Subject prefix"),
        help_text=_("This will be prepended to the subject of all outgoing emails, formatted as [prefix]. "
                    "Choose, for example, a short form of your event name."),
        required=False
    )
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing emails")
    )

    mail_text_signature = I18nFormField(
        label=_("Signature"),
        required=False,
        widget=I18nTextarea,
        help_text=_("This will be attached to every email. Available placeholders: {event}"),
        validators=[PlaceholderValidator(['{event}'])]
    )

    mail_text_order_placed = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {total}, {currency}, {date}, {payment_info}, {url}, "
                    "{invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{event}', '{total}', '{currency}', '{date}', '{payment_info}',
                                          '{url}', '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_order_paid = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {invoice_name}, {invoice_company}, {payment_info}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{invoice_name}', '{invoice_company}', '{payment_info}'])]
    )
    mail_text_order_free = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_order_changed = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_resend_link = I18nFormField(
        label=_("Text (sent by admin)"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_resend_all_links = I18nFormField(
        label=_("Text (requested by user)"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {orders}"),
        validators=[PlaceholderValidator(['{event}', '{orders}'])]
    )
    mail_days_order_expire_warning = forms.IntegerField(
        label=_("Number of days"),
        required=False,
        min_value=0,
        help_text=_("This email will be sent out this many days before the order expires. If the "
                    "value is 0, the mail will never be sent.")
    )
    mail_text_order_expire_warning = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {expire_date}, {invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{expire_date}', '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_waiting_list = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}, {product}, {hours}, {code}"),
        validators=[PlaceholderValidator(['{event}', '{url}', '{product}', '{hours}', '{code}'])]
    )
    mail_text_order_canceled = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {code}, {url}"),
        validators=[PlaceholderValidator(['{event}', '{code}', '{url}'])]
    )
    mail_text_order_custom_mail = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {expire_date}, {event}, {code}, {date}, {url}, "
                    "{invoice_name}, {invoice_company}"),
        validators=[PlaceholderValidator(['{expire_date}', '{event}', '{code}', '{date}', '{url}',
                                          '{invoice_name}', '{invoice_company}'])]
    )
    mail_text_download_reminder = I18nFormField(
        label=_("Text"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}"),
        validators=[PlaceholderValidator(['{event}', '{url}'])]
    )
    smtp_use_custom = forms.BooleanField(
        label=_("Use custom SMTP server"),
        help_text=_("All mail related to your event will be sent over the smtp server specified by you."),
        required=False
    )
    smtp_host = forms.CharField(
        label=_("Hostname"),
        required=False
    )
    smtp_port = forms.IntegerField(
        label=_("Port"),
        required=False
    )
    smtp_username = forms.CharField(
        label=_("Username"),
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

    def clean(self):
        data = self.cleaned_data
        if not data.get('smtp_password') and data.get('smtp_username'):
            # Leave password unchanged if the username is set and the password field is empty.
            # This makes it impossible to set an empty password as long as a username is set, but
            # Python's smtplib does not support password-less schemes anyway.
            data['smtp_password'] = self.initial.get('smtp_password')

        if data.get('smtp_use_tls') and data.get('smtp_use_ssl'):
            raise ValidationError(_('You can activate either SSL or STARTTLS security, but not both at the same time.'))


class DisplaySettingsForm(SettingsForm):
    primary_color = forms.CharField(
        label=_("Primary color"),
        required=False,
        validators=[
            RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                           message=_('Please enter the hexadecimal code of a color, e.g. #990000.'))
        ],
        widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
    )
    logo_image = ExtFileField(
        label=_('Logo image'),
        ext_whitelist=(".png", ".jpg", ".svg", ".gif", ".jpeg"),
        required=False,
        help_text=_('If you provide a logo image, we will by default not show your events name and date '
                    'in the page header. We will show your logo with a maximal height of 120 pixels.')
    )
    frontpage_text = I18nFormField(
        label=_("Frontpage text"),
        required=False,
        widget=I18nTextarea
    )
    show_variations_expanded = forms.BooleanField(
        label=_("Show variations of a product expanded by default"),
        required=False
    )


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
        widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_ticket_download'}),
    )
    ticket_download_nonadm = forms.BooleanField(
        label=_("Generate tickets for non-admission products"),
        required=False,
        widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_ticket_download'}),
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
