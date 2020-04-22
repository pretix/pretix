import json
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from typing import Any

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Model
from django.utils.translation import (
    gettext_lazy as _, gettext_noop, pgettext, pgettext_lazy,
)
from django_countries import countries
from hierarkey.models import GlobalSettingsBase, Hierarkey
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from i18nfield.strings import LazyI18nString
from rest_framework import serializers

from pretix.api.serializers.fields import ListMultipleChoiceField
from pretix.api.serializers.i18n import I18nField
from pretix.base.models.tax import TaxRule
from pretix.base.reldate import (
    RelativeDateField, RelativeDateTimeField, RelativeDateWrapper,
    SerializerRelativeDateField, SerializerRelativeDateTimeField,
)
from pretix.control.forms import MultipleLanguagesWidget, SingleLanguageWidget

allcountries = list(countries)
allcountries.insert(0, ('', _('Select country')))


DEFAULTS = {
    'max_items_per_order': {
        'default': '10',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            min_value=1,
            label=_("Maximum number of items per order"),
            help_text=_("Add-on products will not be counted.")
        )
    },
    'display_net_prices': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show net prices instead of gross prices in the product list (not recommended!)"),
            help_text=_("Independent of your choice, the cart will show gross prices as this is the price that needs to be "
                        "paid"),

        )
    },
    'attendee_names_asked': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for attendee names"),
            help_text=_("Ask for a name for all tickets which include admission to the event."),
        )
    },
    'attendee_names_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require attendee names"),
            help_text=_("Require customers to fill in the names of all attendees."),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_names_asked'}),
        )
    },
    'attendee_emails_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for email addresses per ticket"),
            help_text=_("Normally, pretix asks for one email address per order and the order confirmation will be sent "
                        "only to that email address. If you enable this option, the system will additionally ask for "
                        "individual email addresses for every admission ticket. This might be useful if you want to "
                        "obtain individual addresses for every attendee even in case of group orders. However, "
                        "pretix will send the order confirmation by default only to the one primary email address, not to "
                        "the per-attendee addresses. You can however enable this in the E-mail settings."),
        )
    },
    'attendee_emails_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require email addresses per ticket"),
            help_text=_("Require customers to fill in individual e-mail addresses for all admission tickets. See the "
                        "above option for more details. One email address for the order confirmation will always be "
                        "required regardless of this setting."),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_emails_asked'}),
        )
    },
    'attendee_company_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for company per ticket"),
        )
    },
    'attendee_company_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require company per ticket"),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_company_asked'}),
        )
    },
    'attendee_addresses_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for postal addresses per ticket"),
        )
    },
    'attendee_addresses_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require postal addresses per ticket"),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-attendee_addresses_asked'}),
        )
    },
    'order_email_asked_twice': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for the order email address twice"),
            help_text=_("Require customers to fill in the primary email address twice to avoid errors."),
        )
    },
    'invoice_address_asked': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for invoice address"),
        )
    },
    'invoice_address_not_asked_free': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Do not ask for invoice address if an order is free'),
        )
    },
    'invoice_name_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require customer name"),
        )
    },
    'invoice_attendee_name': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show attendee names on invoices"),
        )
    },
    'invoice_address_required': {
        'default': 'False',
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'type': bool,
        'form_kwargs': dict(
            label=_("Require invoice address"),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
        )
    },
    'invoice_address_company_required': {
        'default': 'False',
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'type': bool,
        'form_kwargs': dict(
            label=_("Require a business addresses"),
            help_text=_('This will require users to enter a company name.'),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_required'}),
        )
    },
    'invoice_address_beneficiary': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for beneficiary"),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
            required=False
        )
    },
    'invoice_address_custom_field': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_("Custom address field"),
            widget=I18nTextInput,
            help_text=_("If you want to add a custom text field, e.g. for a country-specific registration number, to "
                        "your invoice address form, please fill in the label here. This label will both be used for "
                        "asking the user to input their details as well as for displaying the value on the invoice. "
                        "The field will not be required.")
        )
    },
    'invoice_address_vatid': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for VAT ID"),
            help_text=_("Does only work if an invoice address is asked for. VAT ID is not required."),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_invoice_address_asked'}),
        )
    },
    'invoice_address_explanation_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_("Invoice address explanation"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown above the invoice address form during checkout.")
        )
    },
    'invoice_show_payments': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show paid amount on partially paid invoices"),
            help_text=_("If an invoice has already been paid partially, this option will add the paid and pending "
                        "amount to the invoice."),
        )
    },
    'invoice_include_free': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show free products on invoices"),
            help_text=_("Note that invoices will never be generated for orders that contain only free "
                        "products."),
        )
    },
    'invoice_include_expire_date': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show expiration date of order"),
            help_text=_("The expiration date will not be shown if the invoice is generated after the order is paid."),
        )
    },
    'invoice_numbers_consecutive': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Generate invoices with consecutive numbers"),
            help_text=_("If deactivated, the order code will be used in the invoice number."),
        )
    },
    'invoice_numbers_prefix': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Invoice number prefix"),
            help_text=_("This will be prepended to invoice numbers. If you leave this field empty, your event slug will "
                        "be used followed by a dash. Attention: If multiple events within the same organization use the "
                        "same value in this field, they will share their number range, i.e. every full number will be "
                        "used at most once over all of your events. This setting only affects future invoices. You can "
                        "use %Y (with century) %y (without century) to insert the year of the invoice, or %m and %d for "
                        "the day of month."),
        )
    },
    'invoice_numbers_prefix_cancellations': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Invoice number prefix for cancellations"),
            help_text=_("This will be prepended to invoice numbers of cancellations. If you leave this field empty, "
                        "the same numbering scheme will be used that you configured for regular invoices."),
        )
    },
    'invoice_renderer': {
        'default': 'classic',
        'type': str,
    },
    'reservation_time': {
        'default': '30',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwags': dict(
            min_value=0,
            label=_("Reservation period"),
            help_text=_("The number of minutes the items in a user's cart are reserved for this user."),
        )
    },
    'redirect_to_checkout_directly': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_('Directly redirect to check-out after a product has been added to the cart.'),
        )
    },
    'presale_has_ended_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_("End of presale text"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown above the ticket shop once the designated sales timeframe for this event "
                        "is over. You can use it to describe other options to get a ticket, such as a box office.")
        )
    },
    'payment_explanation': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            widget=I18nTextarea,
            widget_kwargs={'attrs': {
                'rows': 3,
            }},
            required=False,
            label=_("Guidance text"),
            help_text=_("This text will be shown above the payment options. You can explain the choices to the user here, "
                        "if you want.")
        )
    },
    'payment_term_days': {
        'default': '14',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Payment term in days'),
            help_text=_("The number of days after placing an order the user has to pay to preserve their reservation. If "
                        "you use slow payment methods like bank transfer, we recommend 14 days. If you only use real-time "
                        "payment methods, we recommend still setting two or three days to allow people to retry failed "
                        "payments."),
            required=True,
            validators=[MinValueValidator(0),
                        MaxValueValidator(1000000)]
        ),
        'serializer_kwargs': dict(
            validators=[MinValueValidator(0),
                        MaxValueValidator(1000000)]
        )
    },
    'payment_term_last': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateField,
        'serializer_class': SerializerRelativeDateField,
        'form_kwargs': dict(
            label=_('Last date of payments'),
            help_text=_("The last date any payments are accepted. This has precedence over the number of "
                        "days configured above. If you use the event series feature and an order contains tickets for "
                        "multiple dates, the earliest date will be used."),
        )
    },
    'payment_term_weekdays': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Only end payment terms on weekdays'),
            help_text=_("If this is activated and the payment term of any order ends on a Saturday or Sunday, it will be "
                        "moved to the next Monday instead. This is required in some countries by civil law. This will "
                        "not effect the last date of payments configured above."),
        )
    },
    'payment_term_expire_automatically': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Automatically expire unpaid orders'),
            help_text=_("If checked, all unpaid orders will automatically go from 'pending' to 'expired' "
                        "after the end of their payment deadline. This means that those tickets go back to "
                        "the pool and can be ordered by other people."),
        )
    },
    'payment_giftcard__enabled': {
        'default': 'True',
        'type': bool
    },
    'payment_resellers__restrict_to_sales_channels': {
        'default': ['resellers'],
        'type': list
    },
    'payment_term_accept_late': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Accept late payments'),
            help_text=_("Accept payments for orders even when they are in 'expired' state as long as enough "
                        "capacity is available. No payments will ever be accepted after the 'Last date of payments' "
                        "configured above."),
        )
    },
    'presale_start_show_date': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show start date"),
            help_text=_("Show the presale start date before presale has started."),
            widget=forms.CheckboxInput,
        )
    },
    'tax_rate_default': {
        'default': None,
        'type': TaxRule
    },
    'invoice_generate': {
        'default': 'False',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=(
                ('False', _('Do not generate invoices')),
                ('admin', _('Only manually in admin panel')),
                ('user', _('Automatically on user request')),
                ('True', _('Automatically for all created orders')),
                ('paid', _('Automatically on payment')),
            ),
        ),
        'form_kwargs': dict(
            label=_("Generate invoices"),
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
    },
    'invoice_reissue_after_modify': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Automatically cancel and reissue invoice on address changes"),
            help_text=_("If customers change their invoice address on an existing order, the invoice will "
                        "automatically be canceled and a new invoice will be issued. This setting does not affect "
                        "changes made through the backend."),
        )
    },
    'invoice_generate_sales_channels': {
        'default': json.dumps(['web']),
        'type': list
    },
    'invoice_address_from': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Address line"),
            widget=forms.Textarea(attrs={
                'rows': 2,
                'placeholder': _(
                    'Albert Einstein Road 52'
                )
            }),
        )
    },
    'invoice_address_from_name': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Company name"),
        )
    },
    'invoice_address_from_zipcode': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            widget=forms.TextInput(attrs={
                'placeholder': '12345'
            }),
            label=_("ZIP code"),
        )
    },
    'invoice_address_from_city': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            widget=forms.TextInput(attrs={
                'placeholder': _('Random City')
            }),
            label=_("City"),
        )
    },
    'invoice_address_from_country': {
        'default': '',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=allcountries,
        ),
        'form_kwargs': dict(
            choices=allcountries,
            label=_("Country"),
        )
    },
    'invoice_address_from_tax_id': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Domestic tax ID"),
            help_text=_("e.g. tax number in Germany, ABN in Australia, …")
        )
    },
    'invoice_address_from_vat_id': {
        'default': '',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("EU VAT ID"),
        )
    },
    'invoice_introductory_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            widget=I18nTextarea,
            widget_kwargs={'attrs': {
                'rows': 3,
                'placeholder': _(
                    'e.g. With this document, we sent you the invoice for your ticket order.'
                )
            }},
            label=_("Introductory text"),
            help_text=_("Will be printed on every invoice above the invoice rows.")
        )
    },
    'invoice_additional_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            widget=I18nTextarea,
            widget_kwargs={'attrs': {
                'rows': 3,
                'placeholder': _(
                    'e.g. Thank you for your purchase! You can find more information on the event at ...'
                )
            }},
            label=_("Additional text"),
            help_text=_("Will be printed on every invoice below the invoice total.")
        )
    },
    'invoice_footer_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            widget=I18nTextarea,
            widget_kwargs={'attrs': {
                'rows': 5,
                'placeholder': _(
                    'e.g. your bank details, legal details like your VAT ID, registration numbers, etc.'
                )
            }},
            label=_("Footer"),
            help_text=_("Will be printed centered and in a smaller font at the end of every invoice page.")
        )
    },
    'invoice_language': {
        'default': '__user__',
        'type': str
    },
    'invoice_email_attachment': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Attach invoices to emails"),
            help_text=_("If invoices are automatically generated for all orders, they will be attached to the order "
                        "confirmation mail. If they are automatically generated on payment, they will be attached to the "
                        "payment confirmation mail. If they are not automatically generated, they will not be attached "
                        "to emails."),
        )
    },
    'show_items_outside_presale_period': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show items outside presale period"),
            help_text=_("Show item details before presale has started and after presale has ended"),
        )
    },
    'timezone': {
        'default': settings.TIME_ZONE,
        'type': str
    },
    'locales': {
        'default': json.dumps([settings.LANGUAGE_CODE]),
        'type': list,
        'serializer_class': ListMultipleChoiceField,
        'serializer_kwargs': dict(
            choices=settings.LANGUAGES,
            required=True,
        ),
        'form_class': forms.MultipleChoiceField,
        'form_kwargs': dict(
            choices=settings.LANGUAGES,
            widget=MultipleLanguagesWidget,
            required=True,
            label=_("Available languages"),
        )
    },
    'locale': {
        'default': settings.LANGUAGE_CODE,
        'type': str,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=settings.LANGUAGES,
            required=True,
        ),
        'form_class': forms.ChoiceField,
        'form_kwargs': dict(
            choices=settings.LANGUAGES,
            widget=SingleLanguageWidget,
            required=True,
            label=_("Default language"),
        )
    },
    'show_dates_on_frontpage': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show event times and dates on the ticket shop"),
            help_text=_("If disabled, no date or time will be shown on the ticket shop's front page. This settings "
                        "does however not affect the display in other locations."),
        )
    },
    'show_date_to': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show event end date"),
            help_text=_("If disabled, only event's start date will be displayed to the public."),
        )
    },
    'show_times': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show dates with time"),
            help_text=_("If disabled, the event's start and end date will be displayed without the time of day."),
        )
    },
    'hide_sold_out': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Hide all products that are sold out"),
        )
    },
    'show_quota_left': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show number of tickets left"),
            help_text=_("Publicly show how many tickets of a certain type are still available."),
        )
    },
    'meta_noindex': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_('Ask search engines not to index the ticket shop'),
        )
    },
    'show_variations_expanded': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show variations of a product expanded by default"),
        )
    },
    'waiting_list_enabled': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Enable waiting list"),
            help_text=_("Once a ticket is sold out, people can add themselves to a waiting list. As soon as a ticket "
                        "becomes available again, it will be reserved for the first person on the waiting list and this "
                        "person will receive an email notification with a voucher that can be used to buy a ticket."),
        )
    },
    'waiting_list_auto': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Automatic waiting list assignments"),
            help_text=_("If ticket capacity becomes free, automatically create a voucher and send it to the first person "
                        "on the waiting list for that product. If this is not active, mails will not be send automatically "
                        "but you can send them manually via the control panel. If you disable the waiting list but keep "
                        "this option enabled, tickets will still be sent out."),
            widget=forms.CheckboxInput(),
        )
    },
    'waiting_list_hours': {
        'default': '48',
        'type': int,
        'serializer_class': serializers.IntegerField,
        'form_class': forms.IntegerField,
        'form_kwargs': dict(
            label=_("Waiting list response time"),
            min_value=6,
            help_text=_("If a ticket voucher is sent to a person on the waiting list, it has to be redeemed within this "
                        "number of hours until it expires and can be re-assigned to the next person on the list."),
            widget=forms.NumberInput(),
        )
    },
    'ticket_download': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Allow users to download tickets"),
            help_text=_("If this is off, nobody can download a ticket."),
        )
    },
    'ticket_download_date': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateTimeField,
        'serializer_class': SerializerRelativeDateTimeField,
        'form_kwargs': dict(
            label=_("Download date"),
            help_text=_("Ticket download will be offered after this date. If you use the event series feature and an order "
                        "contains tickets for multiple event dates, download of all tickets will be available if at least "
                        "one of the event dates allows it."),
        )
    },
    'ticket_download_addons': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Generate tickets for add-on products"),
            help_text=_('By default, tickets are only issued for products selected individually, not for add-on '
                        'products. With this option, a separate ticket is issued for every add-on product as well.'),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_ticket_download',
                                              'data-checkbox-dependency-visual': 'on'}),
        )
    },
    'ticket_download_nonadm': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Generate tickets for all products"),
            help_text=_('If turned off, tickets are only issued for products that are marked as an "admission ticket"'
                        'in the product settings. You can also turn off ticket issuing in every product separately.'),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_ticket_download',
                                              'data-checkbox-dependency-visual': 'on'}),
        )
    },
    'ticket_download_pending': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Generate tickets for pending orders"),
            help_text=_('If turned off, ticket downloads are only possible after an order has been marked as paid.'),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_ticket_download',
                                              'data-checkbox-dependency-visual': 'on'}),
        )
    },
    'event_list_availability': {
        'default': 'True',
        'type': bool
    },
    'event_list_type': {
        'default': 'list',
        'type': str
    },
    'last_order_modification_date': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateTimeField,
        'serializer_class': SerializerRelativeDateTimeField,
        'form_kwargs': dict(
            label=_('Last date of modifications'),
            help_text=_("The last date users can modify details of their orders, such as attendee names or "
                        "answers to questions. If you use the event series feature and an order contains tickets for "
                        "multiple event dates, the earliest date will be used."),
        )
    },
    'cancel_allow_user': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can cancel their unpaid orders"),
        )
    },
    'cancel_allow_user_until': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateTimeField,
        'serializer_class': SerializerRelativeDateTimeField,
        'form_kwargs': dict(
            label=_("Do not allow cancellations after"),
        )
    },
    'cancel_allow_user_paid': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can cancel their paid orders"),
            help_text=_("Paid money will be automatically paid back if the payment method allows it. "
                        "Otherwise, a manual refund will be created for you to process manually."),
        )
    },
    'cancel_allow_user_paid_keep': {
        'default': '0.00',
        'type': Decimal,
        'form_class': forms.DecimalField,
        'serializer_class': serializers.DecimalField,
        'serializer_kwargs': dict(
            max_digits=10, decimal_places=2
        ),
        'form_kwargs': dict(
            label=_("Keep a fixed cancellation fee"),
        )
    },
    'cancel_allow_user_paid_keep_fees': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Keep payment, shipping and service fees"),
        )
    },
    'cancel_allow_user_paid_keep_percentage': {
        'default': '0.00',
        'type': Decimal,
        'form_class': forms.DecimalField,
        'serializer_class': serializers.DecimalField,
        'serializer_kwargs': dict(
            max_digits=10, decimal_places=2
        ),
        'form_kwargs': dict(
            label=_("Keep a percentual cancellation fee"),
        )
    },
    'cancel_allow_user_paid_adjust_fees': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow customers to voluntarily choose a lower refund"),
            help_text=_("With this option enabled, your customers can choose to get a smaller refund to support you.")
        )
    },
    'cancel_allow_user_paid_adjust_fees_explanation': {
        'default': LazyI18nString.from_gettext(gettext_noop(
            'However, if you want us to help keep the lights on here, please consider using the slider below to '
            'request a smaller refund. Thank you!'
        )),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Voluntary lower refund explanation"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown in between the explanation of how the refunds work and the slider "
                        "which your customers can use to choose the amount they would like to receive. You can use it "
                        "e.g. to explain choosing a lower refund will help your organisation.")
        )
    },
    'cancel_allow_user_paid_require_approval': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can only request a cancellation that needs to be approved by the event organizer "
                    "before the order is canceled and a refund is issued."),
        )
    },
    'cancel_allow_user_paid_refund_as_giftcard': {
        'default': 'off',
        'type': str,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=[
                ('off', _('All refunds are issued to the original payment method')),
                ('option', _('Customers can choose between a gift card and a refund to their payment method')),
                ('force', _('All refunds are issued as gift cards')),
            ],
        ),
        'form_class': forms.ChoiceField,
        'form_kwargs': dict(
            label=_('Refund method'),
            choices=[
                ('off', _('All refunds are issued to the original payment method')),
                ('option', _('Customers can choose between a gift card and a refund to their payment method')),
                ('force', _('All refunds are issued as gift cards')),
            ],
            widget=forms.RadioSelect,
            # When adding a new ordering, remember to also define it in the event model
        )
    },
    'cancel_allow_user_paid_until': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateTimeField,
        'serializer_class': SerializerRelativeDateTimeField,
        'form_kwargs': dict(
            label=_("Do not allow cancellations after"),
        )
    },
    'contact_mail': {
        'default': None,
        'type': str,
        'serializer_class': serializers.EmailField,
        'form_class': forms.EmailField,
        'form_kwargs': dict(
            label=_("Contact address"),
            help_text=_("We'll show this publicly to allow attendees to contact you.")
        )
    },
    'imprint_url': {
        'default': None,
        'type': str,
        'form_class': forms.URLField,
        'form_kwargs': dict(
            label=_("Imprint URL"),
            help_text=_("This should point e.g. to a part of your website that has your contact details and legal "
                        "information."),
        ),
        'serializer_class': serializers.URLField,
    },
    'confirm_text': {
        'default': None,
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_('Confirmation text'),
            help_text=_('This text needs to be confirmed by the user before a purchase is possible. You could for example '
                        'link your terms of service here. If you use the Pages feature to publish your terms of service, '
                        'you don\'t need this setting since you can configure it there.'),
            widget=I18nTextarea,
        )
    },
    'mail_html_renderer': {
        'default': 'classic',
        'type': str
    },
    'mail_attach_ical': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Attach calendar files"),
            help_text=_("If enabled, we will attach an .ics calendar file to order confirmation emails."),
        )
    },
    'mail_prefix': {
        'default': None,
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Subject prefix"),
            help_text=_("This will be prepended to the subject of all outgoing emails, formatted as [prefix]. "
                        "Choose, for example, a short form of your event name."),
        )
    },
    'mail_bcc': {
        'default': None,
        'type': str
    },
    'mail_from': {
        'default': settings.MAIL_FROM,
        'type': str,
        'form_class': forms.EmailField,
        'serializer_class': serializers.EmailField,
        'form_kwargs': dict(
            label=_("Sender address"),
            help_text=_("Sender address for outgoing emails"),
        )
    },
    'mail_from_name': {
        'default': None,
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'form_kwargs': dict(
            label=_("Sender name"),
            help_text=_("Sender name used in conjunction with the sender address for outgoing emails. "
                        "Defaults to your event name."),
        )
    },
    'mail_text_signature': {
        'type': LazyI18nString,
        'default': ""
    },
    'mail_text_resend_link': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

you receive this message because you asked us to send you the link
to your order for {event}.

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_resend_all_links': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

somebody requested a list of your orders for {event}.
The list is as follows:

{orders}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

you have been registered for {event} successfully.

You can view the details and status of your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order for {event} was successful. As you only ordered free products,
no payment is required.

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_send_order_free_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_text_order_placed_require_approval': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we successfully received your order for {event}. Since you ordered
a product that requires approval by the event organizer, we ask you to
be patient and wait for our next email.

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_placed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we successfully received your order for {event} with a total value
of {total_with_currency}. Please complete your payment before {expire_date}.

{payment_info}

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_send_order_placed_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_text_order_placed_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

a ticket for {event} has been ordered for you.

You can view the details and status of your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_changed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order for {event} has been changed.

You can view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_paid': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we successfully received your payment for {event}. Thank you!

{payment_info}

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_send_order_paid_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_text_order_paid_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

a ticket for {event} that has been ordered for you is now paid.

You can view the details and status of your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_days_order_expire_warning': {
        'type': int,
        'default': '3'
    },
    'mail_text_order_expire_warning': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we did not yet receive a full payment for your order for {event}.
Please keep in mind that we only guarantee your order if we receive
your payment before {expire_date}.

You can view the payment information and the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_waiting_list': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

you submitted yourself to the waiting list for {event},
for the product {product}.

We now have a ticket ready for you! You can redeem it in our ticket shop
within the next {hours} hours by entering the following voucher code:

{code}

Alternatively, you can just click on the following link:

{url}

Please note that this link is only valid within the next {hours} hours!
We will reassign the ticket to the next person on the list if you do not
redeem the voucher within that timeframe.

Best regards,
Your {event} team"""))
    },
    'mail_text_order_canceled': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order {code} for {event} has been canceled.

You can view the details of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_approved': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we approved your order for {event} and will be happy to welcome you
at our event.

Please continue by paying for your order before {expire_date}.

You can select a payment method and perform the payment here:

{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_denied': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

unfortunately, we denied your order request for {event}.

{comment}

You can view the details of your order here:

{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_custom_mail': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_days_download_reminder': {
        'type': int,
        'default': None
    },
    'mail_send_download_reminder_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_text_download_reminder_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

you are registered for {event}.

If you did not do so already, you can download your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_download_reminder': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

you bought a ticket for {event}.

If you did not do so already, you can download your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'smtp_use_custom': {
        'default': 'False',
        'type': bool
    },
    'smtp_host': {
        'default': '',
        'type': str
    },
    'smtp_port': {
        'default': 587,
        'type': int
    },
    'smtp_username': {
        'default': '',
        'type': str
    },
    'smtp_password': {
        'default': '',
        'type': str
    },
    'smtp_use_tls': {
        'default': 'True',
        'type': bool
    },
    'smtp_use_ssl': {
        'default': 'False',
        'type': bool
    },
    'primary_color': {
        'default': '#8E44B3',
        'type': str,
    },
    'theme_color_success': {
        'default': '#50A167',
        'type': str
    },
    'theme_color_danger': {
        'default': '#D36060',
        'type': str
    },
    'theme_color_background': {
        'default': '#FFFFFF',
        'type': str
    },
    'theme_round_borders': {
        'default': 'True',
        'type': bool
    },
    'primary_font': {
        'default': 'Open Sans',
        'type': str
    },
    'presale_css_file': {
        'default': None,
        'type': str
    },
    'presale_css_checksum': {
        'default': None,
        'type': str
    },
    'presale_widget_css_file': {
        'default': None,
        'type': str
    },
    'presale_widget_css_checksum': {
        'default': None,
        'type': str
    },
    'logo_image': {
        'default': None,
        'type': File
    },
    'logo_image_large': {
        'default': 'False',
        'type': bool
    },
    'logo_show_title': {
        'default': 'True',
        'type': bool
    },
    'organizer_logo_image': {
        'default': None,
        'type': File
    },
    'organizer_logo_image_large': {
        'default': 'False',
        'type': bool
    },
    'og_image': {
        'default': None,
        'type': File
    },
    'invoice_logo_image': {
        'default': None,
        'type': File
    },
    'frontpage_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Frontpage text"),
            widget=I18nTextarea
        )
    },
    'banner_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Banner text (top)"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown above every page of your shop. Please only use this for "
                        "very important messages.")
        )
    },
    'banner_text_bottom': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Banner text (bottom)"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown below every page of your shop. Please only use this for "
                        "very important messages.")
        )
    },
    'voucher_explanation_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Voucher explanation"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown next to the input for a voucher code. You can use it e.g. to explain "
                        "how to obtain a voucher code.")
        )
    },
    'checkout_email_helptext': {
        'default': LazyI18nString.from_gettext(gettext_noop(
            'Make sure to enter a valid email address. We will send you an order '
            'confirmation including a link that you need to access your order later.'
        )),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Help text of the email field"),
            widget_kwargs={'attrs': {'rows': '2'}},
            widget=I18nTextarea
        )
    },
    'order_import_settings': {
        'default': '{}',
        'type': dict
    },
    'organizer_info_text': {
        'default': '',
        'type': LazyI18nString
    },
    'event_team_provisioning': {
        'default': 'True',
        'type': bool
    },
    'update_check_ack': {
        'default': 'False',
        'type': bool
    },
    'update_check_email': {
        'default': '',
        'type': str
    },
    'update_check_perform': {
        'default': 'True',
        'type': bool
    },
    'update_check_result': {
        'default': None,
        'type': dict
    },
    'update_check_result_warning': {
        'default': 'False',
        'type': bool
    },
    'update_check_last': {
        'default': None,
        'type': datetime
    },
    'update_check_id': {
        'default': None,
        'type': str
    },
    'banner_message': {
        'default': '',
        'type': LazyI18nString
    },
    'banner_message_detail': {
        'default': '',
        'type': LazyI18nString
    },
    'opencagedata_apikey': {
        'default': None,
        'type': str
    },
    'leaflet_tiles': {
        'default': None,
        'type': str
    },
    'leaflet_tiles_attribution': {
        'default': None,
        'type': str
    },
    'frontpage_subevent_ordering': {
        'default': 'date_ascending',
        'type': str,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=[
                ('date_ascending', _('Event start time')),
                ('date_descending', _('Event start time (descending)')),
                ('name_ascending', _('Name')),
                ('name_descending', _('Name (descending)')),
            ],
        ),
        'form_class': forms.ChoiceField,
        'form_kwargs': dict(
            label=pgettext('subevent', 'Date ordering'),
            choices=[
                ('date_ascending', _('Event start time')),
                ('date_descending', _('Event start time (descending)')),
                ('name_ascending', _('Name')),
                ('name_descending', _('Name (descending)')),
            ],
            # When adding a new ordering, remember to also define it in the event model
        )
    },
    'name_scheme': {
        'default': 'full',
        'type': str
    },
    'giftcard_length': {
        'default': settings.ENTROPY['giftcard_secret'],
        'type': int
    },
    'seating_allow_blocked_seats_for_channel': {
        'default': [],
        'type': list
    },
}
PERSON_NAME_TITLE_GROUPS = OrderedDict([
    ('english_common', (_('Most common English titles'), (
        'Mr',
        'Ms',
        'Mrs',
        'Miss',
        'Mx',
        'Dr',
        'Professor',
        'Sir'
    ))),
    ('german_common', (_('Most common German titles'), (
        'Dr.',
        'Prof.',
        'Prof. Dr.',
    )))
])
PERSON_NAME_SCHEMES = OrderedDict([
    ('given_family', {
        'fields': (
            ('given_name', _('Given name'), 1),
            ('family_name', _('Family name'), 1),
        ),
        'concatenation': lambda d: ' '.join(str(p) for p in [d.get('given_name', ''), d.get('family_name', '')] if p),
        'sample': {
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'given_family',
        },
    }),
    ('title_given_family', {
        'fields': (
            ('title', pgettext_lazy('person_name', 'Title'), 1),
            ('given_name', _('Given name'), 2),
            ('family_name', _('Family name'), 2),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in [d.get('title', ''), d.get('given_name', ''), d.get('family_name', '')] if p
        ),
        'sample': {
            'title': pgettext_lazy('person_name_sample', 'Dr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'title_given_family',
        },
    }),
    ('title_given_family', {
        'fields': (
            ('title', pgettext_lazy('person_name', 'Title'), 1),
            ('given_name', _('Given name'), 2),
            ('family_name', _('Family name'), 2),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in [d.get('title', ''), d.get('given_name', ''), d.get('family_name', '')] if p
        ),
        'sample': {
            'title': pgettext_lazy('person_name_sample', 'Dr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'title_given_family',
        },
    }),
    ('given_middle_family', {
        'fields': (
            ('given_name', _('First name'), 2),
            ('middle_name', _('Middle name'), 1),
            ('family_name', _('Family name'), 2),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in [d.get('given_name', ''), d.get('middle_name', ''), d.get('family_name', '')] if p
        ),
        'sample': {
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'middle_name': 'M',
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'given_middle_family',
        },
    }),
    ('title_given_middle_family', {
        'fields': (
            ('title', pgettext_lazy('person_name', 'Title'), 1),
            ('given_name', _('First name'), 2),
            ('middle_name', _('Middle name'), 1),
            ('family_name', _('Family name'), 1),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in [d.get('title', ''), d.get('given_name'), d.get('middle_name'), d.get('family_name')] if p
        ),
        'sample': {
            'title': pgettext_lazy('person_name_sample', 'Dr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'middle_name': 'M',
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'title_given_middle_family',
        },
    }),
    ('family_given', {
        'fields': (
            ('family_name', _('Family name'), 1),
            ('given_name', _('Given name'), 1),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in [d.get('family_name', ''), d.get('given_name', '')] if p
        ),
        'sample': {
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'family_given',
        },
    }),
    ('family_nospace_given', {
        'fields': (
            ('given_name', _('Given name'), 1),
            ('family_name', _('Family name'), 1),
        ),
        'concatenation': lambda d: ''.join(
            str(p) for p in [d.get('family_name', ''), d.get('given_name', '')] if p
        ),
        'sample': {
            'given_name': '泽东',
            'family_name': '毛',
            '_scheme': 'family_nospace_given',
        },
    }),
    ('family_comma_given', {
        'fields': (
            ('given_name', _('Given name'), 1),
            ('family_name', _('Family name'), 1),
        ),
        'concatenation': lambda d: (
            str(d.get('family_name', '')) +
            str((', ' if d.get('family_name') and d.get('given_name') else '')) +
            str(d.get('given_name', ''))
        ),
        'sample': {
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'family_comma_given',
        },
    }),
    ('full', {
        'fields': (
            ('full_name', _('Name'), 1),
        ),
        'concatenation': lambda d: str(d.get('full_name', '')),
        'sample': {
            'full_name': pgettext_lazy('person_name_sample', 'John Doe'),
            '_scheme': 'full',
        },
    }),
    ('calling_full', {
        'fields': (
            ('calling_name', _('Calling name'), 1),
            ('full_name', _('Full name'), 2),
        ),
        'concatenation': lambda d: str(d.get('full_name', '')),
        'sample': {
            'full_name': pgettext_lazy('person_name_sample', 'John Doe'),
            'calling_name': pgettext_lazy('person_name_sample', 'John'),
            '_scheme': 'calling_full',
        },
    }),
    ('full_transcription', {
        'fields': (
            ('full_name', _('Full name'), 1),
            ('latin_transcription', _('Latin transcription'), 2),
        ),
        'concatenation': lambda d: str(d.get('full_name', '')),
        'sample': {
            'full_name': '庄司',
            'latin_transcription': 'Shōji',
            '_scheme': 'full_transcription',
        },
    }),
])
COUNTRIES_WITH_STATE_IN_ADDRESS = {
    # Source: http://www.bitboost.com/ref/international-address-formats.html
    # This is not a list of countries that *have* states, this is a list of countries where states
    # are actually *used* in postal addresses. This is obviously not complete and opinionated.
    # Country: [(List of subdivision types as defined by pycountry), (short or long form to be used)]
    'AU': (['State', 'Territory'], 'short'),
    'BR': (['State'], 'short'),
    'CA': (['Province', 'Territory'], 'short'),
    'CN': (['Province', 'Autonomous region', 'Munincipality'], 'long'),
    'MY': (['State'], 'long'),
    'MX': (['State', 'Federal District'], 'short'),
    'US': (['State', 'Outlying area', 'District'], 'short'),
}


settings_hierarkey = Hierarkey(attribute_name='settings')

for k, v in DEFAULTS.items():
    settings_hierarkey.add_default(k, v['default'], v['type'])


def i18n_uns(v):
    try:
        return LazyI18nString(json.loads(v))
    except ValueError:
        return LazyI18nString(str(v))


settings_hierarkey.add_type(LazyI18nString,
                            serialize=lambda s: json.dumps(s.data),
                            unserialize=i18n_uns)
settings_hierarkey.add_type(RelativeDateWrapper,
                            serialize=lambda rdw: rdw.to_string(),
                            unserialize=lambda s: RelativeDateWrapper.from_string(s))


@settings_hierarkey.set_global(cache_namespace='global')
class GlobalSettingsObject(GlobalSettingsBase):
    slug = '_global'


class SettingsSandbox:
    """
    Transparently proxied access to event settings, handling your prefixes for you.

    :param typestr: The first part of the pretix, e.g. ``plugin``
    :param key: The prefix, e.g. the name of your plugin
    :param obj: The event or organizer that should be queried
    """

    def __init__(self, typestr: str, key: str, obj: Model):
        self._event = obj
        self._type = typestr
        self._key = key

    def get_prefix(self):
        return '%s_%s_' % (self._type, self._key)

    def _convert_key(self, key: str) -> str:
        return '%s_%s_%s' % (self._type, self._key, key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith('_'):
            return super().__setattr__(key, value)
        self.set(key, value)

    def __getattr__(self, item: str) -> Any:
        return self.get(item)

    def __getitem__(self, item: str) -> Any:
        return self.get(item)

    def __delitem__(self, key: str) -> None:
        del self._event.settings[self._convert_key(key)]

    def __delattr__(self, key: str) -> None:
        del self._event.settings[self._convert_key(key)]

    def get(self, key: str, default: Any=None, as_type: type=str):
        return self._event.settings.get(self._convert_key(key), default=default, as_type=as_type)

    def set(self, key: str, value: Any):
        self._event.settings.set(self._convert_key(key), value)


def validate_settings(event, settings_dict):
    from pretix.base.signals import validate_event_settings

    if 'locales' in settings_dict and settings_dict['locale'] not in settings_dict['locales']:
        raise ValidationError({
            'locale': _('Your default locale must also be enabled for your event (see box above).')
        })
    if settings_dict.get('attendee_names_required') and not settings_dict.get('attendee_names_asked'):
        raise ValidationError({
            'attendee_names_required': _('You cannot require specifying attendee names if you do not ask for them.')
        })
    if settings_dict.get('attendee_emails_required') and not settings_dict.get('attendee_emails_asked'):
        raise ValidationError({
            'attendee_emails_required': _('You have to ask for attendee emails if you want to make them required.')
        })
    if settings_dict.get('invoice_address_required') and not settings_dict.get('invoice_address_asked'):
        raise ValidationError({
            'invoice_address_required': _('You have to ask for invoice addresses if you want to make them required.')
        })
    if settings_dict.get('invoice_address_company_required') and not settings_dict.get('invoice_address_required'):
        raise ValidationError({
            'invoice_address_company_required': _('You have to require invoice addresses to require for company names.')
        })

    payment_term_last = settings_dict.get('payment_term_last')
    if payment_term_last and event.presale_end:
        if payment_term_last.date(event) < event.presale_end.date():
            raise ValidationError({
                'payment_term_last': _('The last payment date cannot be before the end of presale.')
            })

    validate_event_settings.send(sender=event, settings_dict=settings_dict)
