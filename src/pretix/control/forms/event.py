from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from pytz import common_timezones

from pretix.base.forms import I18nModelForm, SettingsForm
from pretix.base.i18n import I18nFormField, I18nTextarea
from pretix.base.models import Event


class EventCreateForm(I18nModelForm):
    error_messages = {
        'duplicate_slug': _("You already used this slug for a different event. Please choose a new one."),
    }

    class Meta:
        model = Event
        fields = [
            'name',
            'slug',
            'currency',
            'date_from',
            'date_to',
            'presale_start',
            'presale_end'
        ]

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        super().__init__(*args, **kwargs)

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if Event.objects.filter(slug=slug, organizer=self.organizer).exists():
            raise forms.ValidationError(
                self.error_messages['duplicate_slug'],
                code='duplicate_slug'
            )
        return slug


class EventCreateSettingsForm(SettingsForm):
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

    def clean(self):
        data = super().clean()
        if data['locale'] not in data['locales']:
            raise ValidationError({
                'locale': _('Your default locale must also be enebled for your event (see box above).')
            })
        return data


class EventUpdateForm(I18nModelForm):
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
            'is_public',
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
        label=_('Payment term in days'),
        help_text=_("The number of days after placing an order the user has to pay to preserve his reservation."),
    )
    show_items_outside_presale_period = forms.BooleanField(
        label=_("Show items outside presale period"),
        help_text=_("Show item details before presale has started and after presale has ended"),
        required=False
    )
    presale_start_show_date = forms.BooleanField(
        label=_("Show start date"),
        help_text=_("Show the presale start date before presale has started"),
        required=False
    )
    payment_term_last = forms.DateTimeField(
        label=_('Last date of payments'),
        help_text=_("The last date any payments are accepted. This has precedence over the number of "
                    "days configured above."),
        required=False
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
    last_order_modification_date = forms.DateTimeField(
        label=_('Last date of modifications'),
        help_text=_("The last date users can modify details of their orders, such as attendee names or "
                    "answers to questions."),
        required=False
    )
    tax_rate_default = forms.DecimalField(
        label=_('Tax rate for payment fees'),
        help_text=_("The tax rate that applies for additional fees you configured for single payment methods "
                    "(in percent)."),
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
    show_quota_left = forms.BooleanField(
        label=_("Show number of tickets left"),
        help_text=_("Publicly show how many tickets of a certain type are still available."),
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
    invoice_address_asked = forms.BooleanField(
        label=_("Ask for invoice address"),
        required=False
    )
    invoice_address_required = forms.BooleanField(
        label=_("Require invoice address"),
        required=False
    )
    invoice_address_vatid = forms.BooleanField(
        label=_("Ask for VAT ID"),
        help_text=_("Does only work if an invoice address is asked for. VAT ID is not required."),
        required=False
    )
    invoice_generate = forms.BooleanField(
        label=_("Generate invoices"),
        required=False
    )
    invoice_address_from = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5}), required=False,
        label=_("Your address"),
        help_text=_("Will be printed as the sender on invoices. Be sure to include relevant details required in "
                    "your jurisdiction (e.g. your VAT ID).")
    )
    invoice_additional_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5}), required=False,
        label=_("Additional text"),
        help_text=_("Will be printed on every invoice below the invoice total.")
    )
    invoice_language = forms.ChoiceField(
        widget=forms.Select, required=True,
        label=_("Invoice language"),
        choices=[('__user__', _('The user\'s language'))] + settings.LANGUAGES,
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
    imprint_url = forms.URLField(
        label=_("Imprint URL"),
        required=False,
    )
    contact_mail = forms.EmailField(
        label=_("Contact address"),
        required=False,
        help_text=_("Public email address for contacting the organizer")
    )

    def clean(self):
        data = super().clean()
        if data['locale'] not in data['locales']:
            raise ValidationError({
                'locale': _('Your default locale must also be enebled for your event (see box above).')
            })
        if data['attendee_names_required'] and not data['attendee_names_asked']:
            raise ValidationError({
                'attendee_names_required': _('You cannot require specifying attendee names if you do not ask for them.')
            })
        return data


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

    def clean(self):
        cleaned_data = super().clean()
        enabled = cleaned_data.get(self.settingspref + '_enabled') == 'True'
        if not enabled:
            return
        for k, v in self.fields.items():
            val = cleaned_data.get(k)
            if v._required and (val is None or val == ""):
                self.add_error(k, _('This field is required.'))


class MailSettingsForm(SettingsForm):
    mail_prefix = forms.CharField(
        label=_("Subject prefix"),
        help_text=_("This will be prepended to the subject of all outgoing emails. This could be a short form of "
                    "your event name."),
        required=False
    )
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing e-mails")
    )
    mail_text_order_placed = I18nFormField(
        label=_("Placed order"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {total}, {currency}, {date}, {paymentinfo}, {url}")
    )
    mail_text_order_paid = I18nFormField(
        label=_("Paid order"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}")
    )
    mail_text_resend_link = I18nFormField(
        label=_("Resend link"),
        required=False,
        widget=I18nTextarea,
        help_text=_("Available placeholders: {event}, {url}")
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
        widget=forms.PasswordInput
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


class TicketSettingsForm(SettingsForm):
    ticket_download = forms.BooleanField(
        label=_("Use feature"),
        help_text=_("Use pretix to generate tickets for the user to download and print out."),
        required=False
    )
    ticket_download_date = forms.DateTimeField(
        label=_("Download date"),
        help_text=_("Ticket download will be offered after this date."),
        required=True
    )

    def prepare_fields(self):
        # See clean()
        for k, v in self.fields.items():
            v._required = v.required
            v.required = False
            v.widget.is_required = False

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
