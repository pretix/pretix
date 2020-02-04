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
    pgettext, pgettext_lazy, ugettext_lazy as _, ugettext_noop,
)
from django_countries import countries
from hierarkey.models import GlobalSettingsBase, Hierarkey
from i18nfield.forms import I18nFormField, I18nTextarea
from i18nfield.strings import LazyI18nString
from rest_framework import serializers

from pretix.api.serializers.i18n import I18nField
from pretix.base.models.tax import TaxRule
from pretix.base.reldate import RelativeDateWrapper
from pretix.control.forms import MultipleLanguagesWidget, SingleLanguageWidget

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
    },
    'invoice_address_not_asked_free': {
        'default': 'False',
        'type': bool,
    },
    'invoice_name_required': {
        'default': 'False',
        'type': bool,
    },
    'invoice_attendee_name': {
        'default': 'True',
        'type': bool,
    },
    'invoice_address_required': {
        'default': 'False',
        'type': bool,
    },
    'invoice_address_company_required': {
        'default': 'False',
        'type': bool,
    },
    'invoice_address_beneficiary': {
        'default': 'False',
        'type': bool,
    },
    'invoice_address_vatid': {
        'default': 'False',
        'type': bool,
    },
    'invoice_address_explanation_text': {
        'default': '',
        'type': LazyI18nString
    },
    'invoice_include_free': {
        'default': 'True',
        'type': bool,
    },
    'invoice_include_expire_date': {
        'default': 'False',
        'type': bool,
    },
    'invoice_numbers_consecutive': {
        'default': 'True',
        'type': bool,
    },
    'invoice_numbers_prefix': {
        'default': '',
        'type': str,
    },
    'invoice_numbers_prefix_cancellations': {
        'default': '',
        'type': str,
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
        'type': LazyI18nString
    },
    'payment_term_days': {
        'default': '14',
        'type': int
    },
    'payment_term_last': {
        'default': None,
        'type': RelativeDateWrapper,
    },
    'payment_term_weekdays': {
        'default': 'True',
        'type': bool
    },
    'payment_term_expire_automatically': {
        'default': 'True',
        'type': bool
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
        'type': bool
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
        'type': str
    },
    'invoice_generate_sales_channels': {
        'default': json.dumps(['web']),
        'type': list
    },
    'invoice_address_from': {
        'default': '',
        'type': str
    },
    'invoice_introductory_text': {
        'default': '',
        'type': LazyI18nString
    },
    'invoice_additional_text': {
        'default': '',
        'type': LazyI18nString
    },
    'invoice_footer_text': {
        'default': '',
        'type': LazyI18nString
    },
    'invoice_language': {
        'default': '__user__',
        'type': str
    },
    'invoice_email_attachment': {
        'default': 'False',
        'type': bool
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
        'serializer_class': serializers.MultipleChoiceField,
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
        'type': bool
    },
    'ticket_download_date': {
        'default': None,
        'type': RelativeDateWrapper
    },
    'ticket_download_addons': {
        'default': 'False',
        'type': bool
    },
    'ticket_download_nonadm': {
        'default': 'True',
        'type': bool
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
        'type': RelativeDateWrapper
    },
    'cancel_allow_user': {
        'default': 'True',
        'type': bool
    },
    'cancel_allow_user_until': {
        'default': None,
        'type': RelativeDateWrapper,
    },
    'cancel_allow_user_paid': {
        'default': 'False',
        'type': bool,
    },
    'cancel_allow_user_paid_keep': {
        'default': '0.00',
        'type': Decimal,
    },
    'cancel_allow_user_paid_keep_fees': {
        'default': 'False',
        'type': bool,
    },
    'cancel_allow_user_paid_keep_percentage': {
        'default': '0.00',
        'type': Decimal,
    },
    'cancel_allow_user_paid_until': {
        'default': None,
        'type': RelativeDateWrapper,
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
        'type': bool
    },
    'mail_prefix': {
        'default': None,
        'type': str
    },
    'mail_bcc': {
        'default': None,
        'type': str
    },
    'mail_from': {
        'default': settings.MAIL_FROM,
        'type': str
    },
    'mail_from_name': {
        'default': None,
        'type': str
    },
    'mail_text_signature': {
        'type': LazyI18nString,
        'default': ""
    },
    'mail_text_resend_link': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

you receive this message because you asked us to send you the link
to your order for {event}.

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_resend_all_links': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

somebody requested a list of your orders for {event}.
The list is as follows:

{orders}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello {attendee_name},

you have been registered for {event} successfully.

You can view the details and status of your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello {attendee_name},

a ticket for {event} has been ordered for you.

You can view the details and status of your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_changed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

your order for {event} has been changed.

You can view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_paid': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello {attendee_name},

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

your order {code} for {event} has been canceled.

You can view the details of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_approved': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

unfortunately, we denied your order request for {event}.

{comment}

You can view the details of your order here:

{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_custom_mail': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello {attendee_name},

you are registered for {event}.

If you did not do so already, you can download your ticket here:
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_download_reminder': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

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
        'default': LazyI18nString.from_gettext(ugettext_noop(
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
    if settings_dict['attendee_names_required'] and not settings_dict['attendee_names_asked']:
        raise ValidationError({
            'attendee_names_required': _('You cannot require specifying attendee names if you do not ask for them.')
        })
    if settings_dict['attendee_emails_required'] and not settings_dict['attendee_emails_asked']:
        raise ValidationError({
            'attendee_emails_required': _('You have to ask for attendee emails if you want to make them required.')
        })

    validate_event_settings.send(sender=event, settings_dict=settings_dict)
