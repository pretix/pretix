#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel, Heok Hong Low, Ian Williams, Maico Timmerman,
# Sanket Dasgupta, Tobias Kunze, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import operator
from collections import OrderedDict, UserList
from datetime import datetime
from decimal import Decimal
from typing import Any

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import (
    MaxValueValidator, MinValueValidator, RegexValidator,
)
from django.db.models import Model
from django.utils.functional import lazy
from django.utils.text import format_lazy
from django.utils.translation import (
    gettext, gettext_lazy as _, gettext_noop, pgettext, pgettext_lazy,
)
from django_countries.fields import Country
from hierarkey.models import GlobalSettingsBase, Hierarkey
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput
from i18nfield.strings import LazyI18nString
from phonenumbers import PhoneNumber, parse
from rest_framework import serializers

from pretix.api.serializers.fields import (
    ListMultipleChoiceField, UploadedFileField,
)
from pretix.api.serializers.i18n import I18nField, I18nURLField
from pretix.base.forms import I18nURLFormField
from pretix.base.models.tax import VAT_ID_COUNTRIES, TaxRule
from pretix.base.reldate import (
    RelativeDateField, RelativeDateTimeField, RelativeDateWrapper,
    SerializerRelativeDateField, SerializerRelativeDateTimeField,
)
from pretix.control.forms import (
    ExtFileField, FontSelect, MultipleLanguagesWidget, SingleLanguageWidget,
)
from pretix.helpers.countries import CachedCountries


def country_choice_kwargs():
    allcountries = list(CachedCountries())
    allcountries.insert(0, ('', _('Select country')))
    return {
        'choices': allcountries
    }


def primary_font_kwargs():
    from pretix.presale.style import get_fonts

    choices = [('Open Sans', 'Open Sans')]
    choices += sorted([
        (a, {"title": a, "data": v}) for a, v in get_fonts().items() if not v.get('pdf_only', False)
    ], key=lambda a: a[0])
    return {
        'choices': choices,
    }


def invoice_font_kwargs():
    from pretix.presale.style import get_fonts

    choices = [('Open Sans', 'Open Sans')]
    choices += sorted([
        (a, a) for a, v in get_fonts().items()
    ], key=lambda a: a[0])
    return {
        'choices': choices,
    }


def restricted_plugin_kwargs():
    from pretix.base.plugins import get_all_plugins

    plugins_available = [
        (p.module, p.name) for p in get_all_plugins(None)
        if (
            not p.name.startswith('.') and
            getattr(p, 'restricted', False) and
            not hasattr(p, 'is_available')  # this means you should not really use restricted and is_available
        )
    ]
    return {
        'widget': forms.CheckboxSelectMultiple,
        'label': _("Allow usage of restricted plugins"),
        'choices': plugins_available,
    }


class LazyI18nStringList(UserList):
    def __init__(self, init_list=None):
        super().__init__()
        if init_list is not None:
            self.data = [v if isinstance(v, LazyI18nString) else LazyI18nString(v) for v in init_list]

    def serialize(self):
        return json.dumps([s.data for s in self.data])

    @classmethod
    def unserialize(cls, s):
        return cls(json.loads(s))


DEFAULTS = {
    'allowed_restricted_plugins': {
        'default': [],
        'type': list,
        'form_class': forms.MultipleChoiceField,
        'serializer_class': serializers.MultipleChoiceField,
        'form_kwargs': lambda: restricted_plugin_kwargs(),
    },
    'customer_accounts': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow customers to create accounts"),
            help_text=_("This will allow customers to sign up for an account on your ticket shop. This is a prerequisite for some "
                        "advanced features like memberships.")
        )
    },
    'customer_accounts_native': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow customers to log in with email address and password"),
            help_text=_("If disabled, you will need to connect one or more single-sign-on providers."),
            widget=forms.CheckboxInput(attrs={'data-display-dependency': '#id_settings-customer_accounts'}),
        )
    },
    'customer_accounts_link_by_email': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Match orders based on email address"),
            help_text=_("This will allow registered customers to access orders made with the same email address, even if the customer "
                        "was not logged in during the purchase.")
        )
    },
    'reusable_media_active': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Activate re-usable media"),
            help_text=_("The re-usable media feature allows you to connect tickets and gift cards with physical media "
                        "such as wristbands or chip cards that may be re-used for different tickets or gift cards "
                        "later.")
        )
    },
    'reusable_media_type_barcode': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Active"),
        )
    },
    'reusable_media_type_barcode_identifier_length': {
        'default': 24,
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(
            validators=[
                MinValueValidator(12),
                MaxValueValidator(64),
            ]
        ),
        'form_kwargs': dict(
            label=_('Length of barcodes'),
            validators=[
                MinValueValidator(12),
                MaxValueValidator(64),
            ],
            required=True,
            widget=forms.NumberInput(
                attrs={
                    'min': '12',
                    'max': '64',
                },
            ),
        )
    },
    'reusable_media_type_nfc_uid': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Active"),
        )
    },
    'reusable_media_type_nfc_uid_autocreate_giftcard': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Automatically create a new gift card if a previously unknown chip is seen"),
        )
    },
    'reusable_media_type_nfc_uid_autocreate_giftcard_currency': {
        'default': 'EUR',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=[(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES],
        ),
        'form_kwargs': dict(
            choices=[(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES],
            label=_("Gift card currency"),
        )
    },
    'reusable_media_type_nfc_mf0aes': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Active"),
        )
    },
    'reusable_media_type_nfc_mf0aes_autocreate_giftcard': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Automatically create a new gift card if a new chip is encoded"),
        )
    },
    'reusable_media_type_nfc_mf0aes_autocreate_giftcard_currency': {
        'default': 'EUR',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=[(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES],
        ),
        'form_kwargs': dict(
            choices=[(c.alpha_3, c.alpha_3 + " - " + c.name) for c in settings.CURRENCIES],
            label=_("Gift card currency"),
        )
    },
    'reusable_media_type_nfc_mf0aes_random_uid': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Use UID protection feature of NFC chip"),
        )
    },
    'max_items_per_order': {
        'default': '10',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(
            min_value=1,
        ),
        'form_kwargs': dict(
            min_value=1,
            required=True,
            label=_("Maximum number of items per order"),
            help_text=_("Add-on products will not be counted.")
        ),
    },
    'display_net_prices': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show net prices instead of gross prices in the product list (not recommended!)"),
            help_text=_("Independent of your choice, the cart will show gross prices as this is the price that needs to be "
                        "paid."),

        )
    },
    'hide_prices_from_attendees': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Hide prices on attendee ticket page"),
            help_text=_("If a person buys multiple tickets and you send emails to all of the attendees, with this "
                        "option the ticket price will not be shown on the ticket page of the individual attendees. "
                        "The ticket buyer will of course see the price."),

        )
    },
    'system_question_order': {
        'default': {},
        'type': dict,
        'serializer_class': serializers.DictField,
        'serializer_kwargs': lambda: dict(read_only=True, allow_empty=True),
    },
    'attendee_names_asked': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for attendee names"),
            help_text=_("Ask for a name for all personalized tickets."),
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
                        "individual email addresses for every personalized ticket. This might be useful if you want to "
                        "obtain individual addresses for every attendee even in case of group orders. However, "
                        "pretix will send the order confirmation by default only to the one primary email address, not to "
                        "the per-attendee addresses. You can however enable this in the email settings."),
        )
    },
    'attendee_emails_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require email addresses per ticket"),
            help_text=_("Require customers to fill in individual email addresses for all personalized tickets. See the "
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
    'order_phone_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for a phone number per order"),
        )
    },
    'order_phone_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require a phone number per order"),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-order_phone_asked'}),
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
    'invoice_event_location': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show event location on invoices"),
            help_text=_("The event location will be shown below the list of products if it is the same for all "
                        "lines. It will be shown on every line if there are different locations.")
        )
    },
    'invoice_eu_currencies': {
        'default': 'True',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'form_kwargs': dict(
            label=_("Show exchange rates"),
            widget=forms.RadioSelect,
            choices=(
                ('False', _('Never')),
                ('True', _('Based on European Central Bank daily rates, whenever the invoice recipient is in an EU '
                           'country that uses a different currency.')),
                ('CZK', _('Based on Czech National Bank daily rates, whenever the invoice amount is not in CZK.')),
            ),
        ),
        'serializer_kwargs': dict(
            choices=(
                ('False', _('Never')),
                ('True', _('Based on European Central Bank daily rates, whenever the invoice recipient is in an EU '
                           'country that uses a different currency.')),
                ('CZK', _('Based on Czech National Bank daily rates, whenever the invoice amount is not in CZK.')),
            ),
        ),
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
        )
    },
    'invoice_address_custom_field': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_("Custom recipient field"),
            widget=I18nTextInput,
            help_text=_("If you want to add a custom text field, e.g. for a country-specific registration number, to "
                        "your invoice address form, please fill in the label here. This label will both be used for "
                        "asking the user to input their details as well as for displaying the value on the invoice. It will "
                        "be shown on the invoice below the headline. "
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
            help_text=format_lazy(
                _("Only works if an invoice address is asked for. VAT ID is never required and only requested from "
                  "business customers in the following countries: {countries}"),
                countries=lazy(lambda *args: ', '.join(sorted(gettext(Country(cc).name) for cc in VAT_ID_COUNTRIES)), str)()
            ),
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
        'default': 'False',  # default for new events is True
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show expiration date of order"),
            help_text=_("The expiration date will not be shown if the invoice is generated after the order is paid."),
        )
    },
    'invoice_numbers_counter_length': {
        'default': '5',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(),
        'form_kwargs': dict(
            label=_("Minimum length of invoice number after prefix"),
            help_text=_("The part of your invoice number after your prefix will be filled up with leading zeros up to this length, e.g. INV-001 or INV-00001."),
            max_value=12,
            required=True,
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
            validators=[
                RegexValidator(
                    # We actually allow more characters than we name in the error message since some of these characters
                    # are in active use at the time of the introduction of this validation, so we can't really forbid
                    # them, but we don't think they belong in an invoice number and don't want to advertise them.
                    regex="^[a-zA-Z0-9-_%./,&:# ]+$",
                    message=lazy(lambda *args: _('Please only use the characters {allowed} in this field.').format(
                        allowed='A-Z, a-z, 0-9, -./:#'
                    ), str)()
                )
            ],
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
            validators=[
                RegexValidator(
                    # We actually allow more characters than we name in the error message since some of these characters
                    # are in active use at the time of the introduction of this validation, so we can't really forbid
                    # them, but we don't think they belong in an invoice number and don't want to advertise them.
                    regex="^[a-zA-Z0-9-_%./,&:# ]+$",
                    message=lazy(lambda *args: _('Please only use the characters {allowed} in this field.').format(
                        allowed='A-Z, a-z, 0-9, -./:#'
                    ), str)()
                )
            ],
        )
    },
    'invoice_renderer_highlight_order_code': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Highlight order code to make it stand out visibly"),
            help_text=_("Only respected by some invoice renderers."),
        )
    },
    'invoice_renderer_font': {
        'default': 'Open Sans',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': lambda: dict(**invoice_font_kwargs()),
        'form_kwargs': lambda: dict(
            label=_('Font'),
            help_text=_("Only respected by some invoice renderers."),
            required=True,
            **invoice_font_kwargs()
        ),
    },
    'invoice_renderer': {
        'default': 'classic',  # default for new events is 'modern1'
        'type': str,
    },
    'ticket_secret_generator': {
        'default': 'random',
        'type': str,
    },
    'ticket_secret_length': {
        'default': settings.ENTROPY['ticket_secret'],
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(
            validators=[
                MinValueValidator(12),
                MaxValueValidator(64),
            ]
        ),
        'form_kwargs': dict(
            label=_('Length of ticket codes'),
            validators=[
                MinValueValidator(12),
                MaxValueValidator(64),
            ],
            required=True,
            widget=forms.NumberInput(
                attrs={
                    'min': '12',
                    'max': '64',
                    'data-display-dependency': 'input[name=ticket_secret_generator][value=random]',
                },
            ),
        )
    },
    'reservation_time': {
        'default': '30',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(
            min_value=0,
            max_value=60 * 24 * 7,
        ),
        'form_kwargs': dict(
            min_value=0,
            max_value=60 * 24 * 7,
            label=_("Reservation period"),
            required=True,
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
            label=_("Guidance text"),
            help_text=_("This text will be shown above the payment options. You can explain the choices to the user here, "
                        "if you want.")
        )
    },
    'payment_term_mode': {
        'default': 'days',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=(
                ('days', _("in days")),
                ('minutes', _("in minutes"))
            ),
        ),
        'form_kwargs': dict(
            label=_("Set payment term"),
            widget=forms.RadioSelect,
            required=True,
            choices=(
                ('days', _("in days")),
                ('minutes', _("in minutes"))
            ),
            help_text=_("If using days, the order will expire at the end of the last day. "
                        "Using minutes is more exact, but should only be used for real-time payment methods.")
        )
    },
    'payment_term_days': {
        'default': '14',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Payment term in days'),
            widget=forms.NumberInput(
                attrs={
                    'data-display-dependency': '#id_payment_term_mode_0',
                    'data-required-if': '#id_payment_term_mode_0'
                },
            ),
            help_text=_("The number of days after placing an order the user has to pay to preserve their reservation. If "
                        "you use slow payment methods like bank transfer, we recommend 14 days. If you only use real-time "
                        "payment methods, we recommend still setting two or three days to allow people to retry failed "
                        "payments."),
            validators=[MinValueValidator(0),
                        MaxValueValidator(1000000)]
        ),
        'serializer_kwargs': dict(
            validators=[MinValueValidator(0),
                        MaxValueValidator(1000000)]
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
                        "not effect the last date of payments configured below."),
            widget=forms.CheckboxInput(
                attrs={
                    'data-display-dependency': '#id_payment_term_mode_0',
                },
            ),
        )
    },
    'payment_term_minutes': {
        'default': '30',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Payment term in minutes'),
            help_text=_("The number of minutes after placing an order the user has to pay to preserve their reservation. "
                        "Only use this if you exclusively offer real-time payment methods. Please note that for technical reasons, "
                        "the actual time frame might be a few minutes longer before the order is marked as expired."),
            validators=[MinValueValidator(0),
                        MaxValueValidator(1440)],
            widget=forms.NumberInput(
                attrs={
                    'data-display-dependency': '#id_payment_term_mode_1',
                    'data-required-if': '#id_payment_term_mode_1'
                },
            ),
        ),
        'serializer_kwargs': dict(
            validators=[MinValueValidator(0),
                        MaxValueValidator(1440)]
        )
    },
    'payment_term_last': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateField,
        'serializer_class': SerializerRelativeDateField,
        'form_kwargs': dict(
            label=_('Last date of payments'),
            help_text=_("The last date any payments are accepted. This has precedence over the terms "
                        "configured above. If you use the event series feature and an order contains tickets for "
                        "multiple dates, the earliest date will be used."),
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
    'payment_term_expire_delay_days': {
        'default': '0',
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Expiration delay'),
            help_text=_("The order will only actually expire this many days after the expiration date communicated "
                        "to the customer. If you select \"Only end payment terms on weekdays\" above, this will also "
                        "be respected. However, this will not delay beyond the \"last date of payments\" "
                        "configured above, which is always enforced."),
            # Every order in between the official expiry date and the delayed expiry date has a performance penalty
            # for the cron job, so we limit this feature to 30 days to prevent arbitrary numbers of orders needing
            # to be checked.
            min_value=0,
            max_value=30,
        ),
        'serializer_kwargs': dict(
            min_value=0,
            max_value=30,
        ),
    },
    'payment_pending_hidden': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Hide "payment pending" state on customer-facing pages'),
            help_text=_("The payment instructions panel will still be shown to the primary customer, but no indication "
                        "of missing payment will be visible on the ticket pages of attendees who did not buy the ticket "
                        "themselves.")
        )
    },
    'payment_giftcard__enabled': {
        'default': 'True',
        'type': bool
    },
    'payment_giftcard_public_name': {
        'default': LazyI18nString.from_gettext(gettext_noop('Gift card')),
        'type': LazyI18nString
    },
    'payment_giftcard_public_description': {
        'default': LazyI18nString.from_gettext(gettext_noop(
            'If you have a gift card, please enter the gift card code here. If the gift card does not have '
            'enough credit to pay for the full order, you will be shown this page again and you can either '
            'redeem another gift card or select a different payment method for the difference.'
        )),
        'type': LazyI18nString
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
                ('paid', _('Automatically on payment or when required by payment method')),
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
                ('paid', _('Automatically on payment or when required by payment method')),
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
    'invoice_regenerate_allowed': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow to update existing invoices"),
            help_text=_("By default, invoices can never again be changed once they are issued. In most countries, we "
                        "recommend to leave this option turned off and always issue a new invoice if a change needs "
                        "to be made."),
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
        'serializer_kwargs': lambda: dict(**country_choice_kwargs()),
        'form_kwargs': lambda: dict(label=_('Country'), **country_choice_kwargs()),
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
        'default': 'False',  # default for new events is True
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
    'invoice_email_organizer': {
        'default': '',
        'type': str,
        'form_class': forms.EmailField,
        'serializer_class': serializers.EmailField,
        'form_kwargs': dict(
            label=_("Email address to receive a copy of each invoice"),
            help_text=_("Each newly created invoice will be sent to this email address shortly after creation. You can "
                        "use this for an automated import of invoices to your accounting system. The invoice will be "
                        "the only attachment of the email."),
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
    'region': {
        'default': None,
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': lambda: dict(**country_choice_kwargs()),
        'form_kwargs': lambda: dict(
            label=_('Region'),
            help_text=_('Will be used to determine date and time formatting as well as default country for customer '
                        'addresses and phone numbers. For formatting, this takes less priority than the language and '
                        'is therefore mostly relevant for languages used in different regions globally (like English).'),
            **country_choice_kwargs()
        ),
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
        'serializer_kwargs': dict(
            min_value=1,
        ),
        'form_kwargs': dict(
            label=_("Waiting list response time"),
            min_value=1,
            required=True,
            help_text=_("If a ticket voucher is sent to a person on the waiting list, it has to be redeemed within this "
                        "number of hours until it expires and can be re-assigned to the next person on the list."),
            widget=forms.NumberInput(),
        )
    },
    'waiting_list_names_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for a name"),
            help_text=_("Ask for a name when signing up to the waiting list."),
        )
    },
    'waiting_list_names_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require name"),
            help_text=_("Require a name when signing up to the waiting list.."),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-waiting_list_names_asked'}),
        )
    },
    'waiting_list_phones_asked': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Ask for a phone number"),
            help_text=_("Ask for a phone number when signing up to the waiting list."),
        )
    },
    'waiting_list_phones_required': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Require phone number"),
            help_text=_("Require a phone number when signing up to the waiting list.."),
            widget=forms.CheckboxInput(attrs={'data-checkbox-dependency': '#id_settings-waiting_list_phones_asked'}),
        )
    },
    'waiting_list_phones_explanation_text': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'serializer_class': I18nField,
        'form_kwargs': dict(
            label=_("Phone number explanation"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("If you ask for a phone number, explain why you do so and what you will use the phone number for.")
        )
    },
    'waiting_list_limit_per_user': {
        'default': '1',
        'type': int,
        'serializer_class': serializers.IntegerField,
        'form_class': forms.IntegerField,
        'serializer_kwargs': dict(
            min_value=1,
        ),
        'form_kwargs': dict(
            label=_("Maximum number of entries per email address for the same product"),
            min_value=1,
            required=True,
            widget=forms.NumberInput(),
        )
    },
    'show_checkin_number_user': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Show number of check-ins to customer"),
            help_text=_('With this option enabled, your customers will be able to see how many times they entered '
                        'the event. This is usually not necessary, but might be useful in combination with tickets '
                        'that are usable a specific number of times, so customers can see how many times they have '
                        'already been used. Exits or failed scans will not be counted, and the user will not see '
                        'the different check-in lists.'),
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
            label=_("Generate tickets for add-on products and bundled products"),
            help_text=_('By default, tickets are only issued for products selected individually, not for add-on products '
                        'or bundled products. With this option, a separate ticket is issued for every add-on product '
                        'or bundled product as well.'),
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
    'ticket_download_require_validated_email': {
        'default': 'False',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_("Do not issue ticket before email address is validated"),
            help_text=_("If turned on, tickets will not be offered for download directly after purchase. They will "
                        "be attached to the payment confirmation email (if the file size is not too large), and the "
                        "customer will be able to download them from the page as soon as they clicked a link in "
                        "the email. Does not affect orders performed through other sales channels."),
        )
    },
    'low_availability_percentage': {
        'default': None,
        'type': int,
        'serializer_class': serializers.IntegerField,
        'form_class': forms.IntegerField,
        'serializer_kwargs': dict(
            min_value=0,
            max_value=100,
        ),
        'form_kwargs': dict(
            label=_('Low availability threshold'),
            help_text=_('If the availability of tickets falls below this percentage, the event (or a date, if it is an '
                        'event series) will be highlighted to have low availability in the event list or calendar. If '
                        'you keep this option empty, low availability will not be shown publicly.'),
            min_value=0,
            max_value=100,
            required=False
        )
    },
    'event_list_availability': {
        'default': 'True',
        'type': bool,
        'serializer_class': serializers.BooleanField,
        'form_class': forms.BooleanField,
        'form_kwargs': dict(
            label=_('Show availability in event overviews'),
            help_text=_('If checked, the list of events will show if events are sold out. This might '
                        'make for longer page loading times if you have lots of events and the shown status might be out '
                        'of date for up to two minutes.'),
            required=False
        )
    },
    'event_list_type': {
        'default': 'list',  # default for new events is 'calendar'
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=(
                ('list', _('List')),
                ('week', _('Week calendar')),
                ('calendar', _('Month calendar')),
            )
        ),
        'form_kwargs': dict(
            label=_('Default overview style'),
            choices=(
                ('list', _('List')),
                ('week', _('Week calendar')),
                ('calendar', _('Month calendar')),
            ),
            help_text=_('If your event series has more than 50 dates in the future, only the month or week calendar can be used.')
        ),
    },
    'event_list_available_only': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Hide all unavailable dates from calendar or list views"),
            help_text=_("This option currently only affects the calendar of this event series, not the organizer-wide "
                        "calendar.")
        )
    },
    'event_calendar_future_only': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Hide all past dates from calendar"),
            help_text=_("This option currently only affects the calendar of this event series, not the organizer-wide "
                        "calendar.")
        )
    },
    'allow_modifications_after_checkin': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow customers to modify their information after they checked in."),
        )
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
    'change_allow_user_variation': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can change the variation of the products they purchased"),
        )
    },
    'change_allow_user_addons': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can change their selected add-on products"),
        )
    },
    'change_allow_user_price': {
        'default': 'gte',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': dict(
            choices=(
                ('gte', _('Only allow changes if the resulting price is higher or equal than the previous price.')),
                ('gt', _('Only allow changes if the resulting price is higher than the previous price.')),
                ('eq', _('Only allow changes if the resulting price is equal to the previous price.')),
                ('any', _('Allow changes regardless of price, even if this results in a refund.')),
            )
        ),
        'form_kwargs': dict(
            label=_("Requirement for changed prices"),
            choices=(
                ('gte', _('Only allow changes if the resulting price is higher or equal than the previous price.')),
                ('gt', _('Only allow changes if the resulting price is higher than the previous price.')),
                ('eq', _('Only allow changes if the resulting price is equal to the previous price.')),
                ('any', _('Allow changes regardless of price, even if this results in a refund.')),
            ),
            widget=forms.RadioSelect,
        ),
    },
    'change_allow_user_until': {
        'default': None,
        'type': RelativeDateWrapper,
        'form_class': RelativeDateTimeField,
        'serializer_class': SerializerRelativeDateTimeField,
        'form_kwargs': dict(
            label=_("Do not allow changes after"),
        )
    },
    'change_allow_user_if_checked_in': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow change even though the ticket has already been checked in"),
            help_text=_("By default, order changes are disabled after any ticket in the order has been checked in. "
                        "If you check this box, this requirement is lifted. It is still not possible to remove an "
                        "add-on product that has already been checked in individually. Use with care, and preferably "
                        "only in combination with a limitation on price changes above."),
        )
    },
    'change_allow_attendee': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Allow individual attendees to change their ticket"),
            help_text=_("By default, only the person who ordered the tickets can make any changes. If you check this "
                        "box, individual attendees can also make changes. However, individual attendees can always "
                        "only make changes that do not change the total price of the order. Such changes can always "
                        "only be made by the main customer."),
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
    'cancel_allow_user_unpaid_keep': {
        'default': '0.00',
        'type': Decimal,
        'form_class': forms.DecimalField,
        'serializer_class': serializers.DecimalField,
        'serializer_kwargs': dict(
            max_digits=13, decimal_places=2
        ),
        'form_kwargs': dict(
            label=_("Charge a fixed cancellation fee"),
            help_text=_("Only affects orders pending payments, a cancellation fee for free orders is never charged. "
                        "Note that it will be your responsibility to claim the cancellation fee from the user."),
        )
    },
    'cancel_allow_user_unpaid_keep_fees': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Charge payment, shipping and service fees"),
            help_text=_("Only affects orders pending payments, a cancellation fee for free orders is never charged. "
                        "Note that it will be your responsibility to claim the cancellation fee from the user."),
        )
    },
    'cancel_allow_user_unpaid_keep_percentage': {
        'default': '0.00',
        'type': Decimal,
        'form_class': forms.DecimalField,
        'serializer_class': serializers.DecimalField,
        'serializer_kwargs': dict(
            max_digits=13, decimal_places=2
        ),
        'form_kwargs': dict(
            label=_("Charge a percentual cancellation fee"),
            help_text=_("Only affects orders pending payments, a cancellation fee for free orders is never charged. "
                        "Note that it will be your responsibility to claim the cancellation fee from the user."),
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
            max_digits=13, decimal_places=2
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
            max_digits=13, decimal_places=2
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
                        "e.g. to explain choosing a lower refund will help your organization.")
        )
    },
    'cancel_allow_user_paid_adjust_fees_step': {
        'default': None,
        'type': Decimal,
        'form_class': forms.DecimalField,
        'serializer_class': serializers.DecimalField,
        'serializer_kwargs': dict(
            max_digits=13, decimal_places=2
        ),
        'form_kwargs': dict(
            max_digits=13, decimal_places=2,
            label=_("Step size for reduction amount"),
            help_text=_('By default, customers can choose an arbitrary amount for you to keep. If you set this to e.g. '
                        '10, they will only be able to choose values in increments of 10.')
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
    'cancel_allow_user_paid_require_approval_fee_unknown': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Do not show the cancellation fee to users when they request cancellation."),
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
                ('manually', _('Do not handle refunds automatically at all')),
            ],
        ),
        'form_class': forms.ChoiceField,
        'form_kwargs': dict(
            label=_('Refund method'),
            choices=[
                ('off', _('All refunds are issued to the original payment method')),
                ('option', _('Customers can choose between a gift card and a refund to their payment method')),
                ('force', _('All refunds are issued as gift cards')),
                ('manually', _('Do not handle refunds automatically at all')),
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
    'privacy_url': {
        'default': None,
        'type': LazyI18nString,
        'form_class': I18nURLFormField,
        'form_kwargs': dict(
            label=_("Privacy Policy URL"),
            help_text=_("This should point e.g. to a part of your website that explains how you use data gathered in "
                        "your ticket shop."),
            widget=I18nTextInput,
        ),
        'serializer_class': I18nURLField,
    },
    'confirm_texts': {
        'default': LazyI18nStringList(),
        'type': LazyI18nStringList,
        'serializer_class': serializers.ListField,
        'serializer_kwargs': lambda: dict(child=I18nField()),
    },
    'mail_html_renderer': {
        'default': 'classic',
        'type': str
    },
    'mail_attach_tickets': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Attach ticket files"),
            help_text=format_lazy(
                _("Tickets will never be attached if they're larger than {size} to avoid email delivery problems."),
                size='4 MB'
            ),
        )
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
    'mail_attach_ical_paid_only': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Attach calendar files only after order has been paid"),
            help_text=_("Use this if you e.g. put a private access link into the calendar file to make sure people only "
                        "receive it after their payment was confirmed."),
        )
    },
    'mail_attach_ical_description': {
        'default': '',
        'type': LazyI18nString,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Event description"),
            widget=I18nTextarea,
            help_text=_(
                "You can use this to share information with your attendees, such as travel information or the link to a digital event. "
                "If you keep it empty, we will put a link to the event shop, the admission time, and your organizer name in there. "
                "We do not allow using placeholders with sensitive person-specific data as calendar entries are often shared with an "
                "unspecified number of people."
            ),
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
        'default': settings.MAIL_FROM_ORGANIZERS,
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
    'mail_sales_channel_placed_paid': {
        'default': ['web'],
        'type': list,
    },
    'mail_sales_channel_download_reminder': {
        'default': ['web'],
        'type': list,
    },
    'mail_text_signature': {
        'type': LazyI18nString,
        'default': ""
    },
    'mail_subject_resend_link': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order: {code}")),
    },
    'mail_subject_resend_link_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your event registration: {code}")),
    },
    'mail_text_resend_link': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

you receive this message because you asked us to send you the link
to your order for {event}.

You can change your order details and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_resend_all_links': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your orders for {event}")),
    },
    'mail_text_resend_all_links': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

somebody requested a list of your orders for {event}.
The list is as follows:

{orders}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your event registration: {code}")),
    },
    'mail_text_order_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

you have been registered for {event} successfully.

You can view the details and status of your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_send_order_free_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_order_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order: {code}")),
    },
    'mail_text_order_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order for {event} was successful. As you only ordered free products,
no payment is required.

You can change your order details and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_placed_require_approval': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order: {code}")),
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
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_placed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order: {code}")),
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
Your {event} team"""))  # noqa: W291
    },
    'mail_attachment_new_order': {
        'default': None,
        'type': File,
        'form_class': ExtFileField,
        'form_kwargs': dict(
            label=_('Attachment for new orders'),
            ext_whitelist=(".pdf",),
            max_size=settings.FILE_UPLOAD_MAX_SIZE_EMAIL_AUTO_ATTACHMENT,
            help_text=format_lazy(
                _(
                    'This file will be attached to the first email that we send for every new order. Therefore it will be '
                    'combined with the "Placed order", "Free order", or "Received order" texts from above. It will be sent '
                    'to both order contacts and attendees. You can use this e.g. to send your terms of service. Do not use '
                    'it to send non-public information as this file might be sent before payment is confirmed or the order '
                    'is approved. To avoid this vital email going to spam, you can only upload PDF files of up to {size} MB.'
                ),
                size=settings.FILE_UPLOAD_MAX_SIZE_EMAIL_AUTO_ATTACHMENT // (1024 * 1024),
            )
        ),
        'serializer_class': UploadedFileField,
        'serializer_kwargs': dict(
            allowed_types=[
                'application/pdf'
            ],
            max_size=settings.FILE_UPLOAD_MAX_SIZE_EMAIL_AUTO_ATTACHMENT,
        )
    },
    'mail_send_order_placed_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_order_placed_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your event registration: {code}")),
    },
    'mail_text_order_placed_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

a ticket for {event} has been ordered for you.

You can view the details and status of your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_changed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order has been changed: {code}")),
    },
    'mail_text_order_changed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order for {event} has been changed.

You can view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_paid': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Payment received for your order: {code}")),
    },
    'mail_text_order_paid': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we successfully received your payment for {event}. Thank you!

{payment_info}

You can change your order details and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_send_order_paid_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_order_paid_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Event registration confirmed: {code}")),
    },
    'mail_text_order_paid_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

a ticket for {event} that has been ordered for you is now paid.

You can view the details and status of your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_days_order_expire_warning': {
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'serializer_kwargs': dict(
            min_value=0,
        ),
        'form_kwargs': dict(
            label=_("Number of days"),
            min_value=0,
            help_text=_("This email will be sent out this many days before the order expires. If the "
                        "value is 0, the mail will never be sent.")
        ),
        'type': int,
        'default': '3'
    },
    'mail_subject_order_expire_warning': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order is about to expire: {code}")),
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
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_pending_warning': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your order is pending payment: {code}")),
    },
    'mail_text_order_pending_warning': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we did not yet receive a full payment for your order for {event}.
Please keep in mind that you are required to pay before {expire_date}.

You can view the payment information and the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_incomplete_payment': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Incomplete payment received: {code}")),
    },
    'mail_text_order_incomplete_payment': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we received a payment for your order for {event}.

Unfortunately, the received amount is less than the full amount
required. Your order is therefore still considered unpaid, as it is
missing additional payment of **{pending_sum}**.

You can view the payment information and the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_payment_failed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Payment failed for your order: {code}")),
    },
    'mail_text_order_payment_failed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your payment attempt for your order for {event} has failed.

Your order is still valid and you can try to pay again using the same or a different payment method. Please complete your payment before {expire_date}.

You can retry the payment and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_waiting_list': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("You have been selected from the waitinglist for {event}")),
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

If you do NOT need a ticket any more, we kindly ask you to click the
following link to let us know. This way, we can send the ticket as quickly
as possible to the next person on the waiting list:

{url_remove}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_canceled': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Order canceled: {code}")),
    },
    'mail_text_order_canceled': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

your order {code} for {event} has been canceled.

{comment}

You can view the details of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_approved': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Order approved and awaiting payment: {code}")),
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
Your {event} team"""))  # noqa: W291
    },
    'mail_send_order_approved_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_order_approved_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your event registration: {code}")),
    },
    'mail_text_order_approved_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we approved a ticket ordered for you for {event}.

You can view the details and status of your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_approved_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Order approved and confirmed: {code}")),
    },
    'mail_text_order_approved_free': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we approved your order for {event} and will be happy to welcome you
at our event. As you only ordered free products, no payment is required.

You can change your order details and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_send_order_approved_free_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_order_approved_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your event registration: {code}")),
    },
    'mail_text_order_approved_free_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

we approved a ticket ordered for you for {event}.

You can view the details and status of your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_order_denied': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Order denied: {code}")),
    },
    'mail_text_order_denied': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

unfortunately, we denied your order request for {event}.

{comment}

You can view the details of your order here:

{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_text_order_custom_mail': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

You can change your order details and view the status of your order at
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_days_download_reminder': {
        'type': int,
        'default': None
    },
    'mail_send_download_reminder_attendee': {
        'type': bool,
        'default': 'False'
    },
    'mail_subject_download_reminder_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your ticket is ready for download: {code}")),
    },
    'mail_text_download_reminder_attendee': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {attendee_name},

you are registered for {event}.

If you did not do so already, you can download your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_download_reminder': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Your ticket is ready for download: {code}")),
    },
    'mail_text_download_reminder': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello,

you bought a ticket for {event}.

If you did not do so already, you can download your ticket here:
{url}

Best regards,  
Your {event} team"""))  # noqa: W291
    },
    'mail_subject_customer_registration': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Activate your account at {organizer}")),
    },
    'mail_text_customer_registration': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {name},

thank you for signing up for an account at {organizer}!

To activate your account and set a password, please click here:

{url}

This link is valid for one day.

If you did not sign up yourself, please ignore this email.

Best regards,  

Your {organizer} team"""))  # noqa: W291
    },
    'mail_subject_customer_email_change': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Confirm email address for your account at {organizer}")),
    },
    'mail_text_customer_email_change': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {name},

you requested to change the email address of your account at {organizer}!

To confirm the change, please click here:

{url}

This link is valid for one day.

If you did not request this, please ignore this email.

Best regards,  

Your {organizer} team"""))  # noqa: W291
    },
    'mail_subject_customer_reset': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("Set a new password for your account at {organizer}")),
    },
    'mail_text_customer_reset': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(gettext_noop("""Hello {name},

you requested a new password for your account at {organizer}!

To set a new password, please click here:

{url}

This link is valid for one day.

If you did not request a new password, please ignore this email.

Best regards,  

Your {organizer} team"""))  # noqa: W291
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
        'default': settings.PRETIX_PRIMARY_COLOR,
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'serializer_kwargs': dict(
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
        ),
        'form_kwargs': dict(
            label=_("Primary color"),
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
            required=True,
            widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
        ),
    },
    'theme_color_success': {
        'default': '#50a167',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'serializer_kwargs': dict(
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
        ),
        'form_kwargs': dict(
            label=_("Accent color for success"),
            help_text=_("We strongly suggest to use a shade of green."),
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
            required=True,
            widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
        ),
    },
    'theme_color_danger': {
        'default': '#c44f4f',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'serializer_kwargs': dict(
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
        ),
        'form_kwargs': dict(
            label=_("Accent color for errors"),
            help_text=_("We strongly suggest to use a shade of red."),
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
            required=True,
            widget=forms.TextInput(attrs={'class': 'colorpickerfield'})
        ),
    },
    'theme_color_background': {
        'default': '#f5f5f5',
        'type': str,
        'form_class': forms.CharField,
        'serializer_class': serializers.CharField,
        'serializer_kwargs': dict(
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
        ),
        'form_kwargs': dict(
            label=_("Page background color"),
            validators=[
                RegexValidator(regex='^#[0-9a-fA-F]{6}$',
                               message=_('Please enter the hexadecimal code of a color, e.g. #990000.')),
            ],
            required=True,
            widget=forms.TextInput(attrs={'class': 'colorpickerfield no-contrast'})
        ),
    },
    'theme_round_borders': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Use round edges"),
        )
    },
    'widget_use_native_spinners': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Use native spinners in the widget instead of custom ones for numeric inputs such as quantity."),
        )
    },
    'primary_font': {
        'default': 'Open Sans',
        'type': str,
        'form_class': forms.ChoiceField,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': lambda: dict(**primary_font_kwargs()),
        'form_kwargs': lambda: dict(
            label=_('Font'),
            help_text=_('Only respected by modern browsers.'),
            required=True,
            widget=FontSelect,
            **primary_font_kwargs()
        ),
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
        'type': File,
        'form_class': ExtFileField,
        'form_kwargs': dict(
            label=_('Header image'),
            ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
            help_text=_('If you provide a logo image, we will by default not show your event name and date '
                        'in the page header. By default, we show your logo with a size of up to 1140x120 pixels. You '
                        'can increase the size with the setting below. We recommend not using small details on the picture '
                        'as it will be resized on smaller screens.')
        ),
        'serializer_class': UploadedFileField,
        'serializer_kwargs': dict(
            allowed_types=[
                'image/png', 'image/jpeg', 'image/gif'
            ],
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        )

    },
    'logo_image_large': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Use header image in its full size'),
            help_text=_('We recommend to upload a picture at least 1170 pixels wide.'),
        )
    },
    'logo_show_title': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Show event title even if a header image is present'),
            help_text=_('The title will only be shown on the event front page. If no header image is uploaded for the event, but the header image '
                        'from the organizer profile is used, this option will be ignored and the event title will always be shown.'),
        )
    },
    'organizer_logo_image': {
        'default': None,
        'type': File,
        'form_class': ExtFileField,
        'form_kwargs': dict(
            label=_('Header image'),
            ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
            help_text=_('If you provide a logo image, we will by default not show your organization name '
                        'in the page header. By default, we show your logo with a size of up to 1140x120 pixels. You '
                        'can increase the size with the setting below. We recommend not using small details on the picture '
                        'as it will be resized on smaller screens.')
        ),
        'serializer_class': UploadedFileField,
        'serializer_kwargs': dict(
            allowed_types=[
                'image/png', 'image/jpeg', 'image/gif'
            ],
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        )
    },
    'organizer_logo_image_large': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Use header image in its full size'),
            help_text=_('We recommend to upload a picture at least 1170 pixels wide.'),
        )
    },
    'organizer_logo_image_inherit': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Use header image also for events without an individually uploaded logo'),
        )
    },
    'og_image': {
        'default': None,
        'type': File,
        'form_class': ExtFileField,
        'form_kwargs': dict(
            label=_('Social media image'),
            ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
            help_text=_('This picture will be used as a preview if you post links to your ticket shop on social media. '
                        'Facebook advises to use a picture size of 1200 x 630 pixels, however some platforms like '
                        'WhatsApp and Reddit only show a square preview, so we recommend to make sure it still looks good '
                        'only the center square is shown. If you do not fill this, we will use the logo given above.')
        ),
        'serializer_class': UploadedFileField,
        'serializer_kwargs': dict(
            allowed_types=[
                'image/png', 'image/jpeg', 'image/gif'
            ],
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        )
    },
    'invoice_logo_image': {
        'default': None,
        'type': File,
        'form_class': ExtFileField,
        'form_kwargs': dict(
            label=_('Logo image'),
            ext_whitelist=(".png", ".jpg", ".gif", ".jpeg"),
            required=False,
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
            help_text=_('We will show your logo with a maximal height and width of 2.5 cm.')
        ),
        'serializer_class': UploadedFileField,
        'serializer_kwargs': dict(
            allowed_types=[
                'image/png', 'image/jpeg', 'image/gif'
            ],
            max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE,
        )
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
    'event_info_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('Info text'),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_('Not displayed anywhere by default, but if you want to, you can use this e.g. in ticket templates.')
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
    'attendee_data_explanation_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Attendee data explanation"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '2'}},
            help_text=_("This text will be shown above the questions asked for every personalized product. You can use it e.g. to explain "
                        "why you need information from them.")
        )
    },
    'checkout_success_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Additional success message"),
            help_text=_("This message will be shown after an order has been created successfully. It will be shown in additional "
                        "to the default text."),
            widget_kwargs={'attrs': {'rows': '2'}},
            widget=I18nTextarea
        )
    },
    'checkout_phone_helptext': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Help text of the phone number field"),
            widget_kwargs={'attrs': {'rows': '2'}},
            widget=I18nTextarea
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
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('Info text'),
            widget=I18nTextarea,
            help_text=_('Not displayed anywhere by default, but if you want to, you can use this e.g. in ticket templates.')
        )
    },
    'event_team_provisioning': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Allow creating a new team during event creation'),
            help_text=_('Users that do not have access to all events under this organizer, must select one of their teams '
                        'to have access to the created event. This setting allows users to create an event-specified team'
                        ' on-the-fly, even when they do not have \"Can change teams and permissions\" permission.'),
        )
    },
    'license_check_completed': {
        'default': None,
        'type': datetime
    },
    'license_check_input': {
        'default': '{}',
        'type': dict
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
    'mapquest_apikey': {
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
    'organizer_link_back': {
        'default': 'False',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_('Link back to organizer overview on all event pages'),
        )
    },
    'organizer_homepage_text': {
        'default': '',
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('Homepage text'),
            widget=I18nTextarea,
            help_text=_('This will be displayed on the organizer homepage.')
        )
    },
    'name_scheme': {
        'default': 'full',  # default for new events is 'given_family'
        'type': str,
        'serializer_class': serializers.ChoiceField,
        'serializer_kwargs': {},
    },
    'giftcard_length': {
        'default': settings.ENTROPY['giftcard_secret'],
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Length of gift card codes'),
            help_text=_('The system generates by default {}-character long gift card codes. However, if a different length '
                        'is required, it can be set here.'.format(settings.ENTROPY['giftcard_secret'])),
        )
    },
    'giftcard_expiry_years': {
        'default': None,
        'type': int,
        'form_class': forms.IntegerField,
        'serializer_class': serializers.IntegerField,
        'form_kwargs': dict(
            label=_('Validity of gift card codes in years'),
            help_text=_('If you set a number here, gift cards will by default expire at the end of the year after this '
                        'many years. If you keep it empty, gift cards do not have an explicit expiry date.'),
        )
    },
    'cookie_consent': {
        'default': 'False',
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Enable cookie consent management features"),
        ),
        'type': bool,
    },
    'cookie_consent_dialog_text': {
        'default': LazyI18nString.from_gettext(gettext_noop(
            'By clicking "Accept all cookies", you agree to the storing of cookies and use of similar technologies on '
            'your device.'
        )),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Dialog text"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '3', 'data-display-dependency': '#id_settings-cookie_consent'}},
        )
    },
    'cookie_consent_dialog_text_secondary': {
        'default': LazyI18nString.from_gettext(gettext_noop(
            'We use cookies and similar technologies to gather data that allows us to improve this website and our '
            'offerings. If you do not agree, we will only use cookies if they are essential to providing the services '
            'this website offers.'
        )),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_("Secondary dialog text"),
            widget=I18nTextarea,
            widget_kwargs={'attrs': {'rows': '3', 'data-display-dependency': '#id_settings-cookie_consent'}},
        )
    },
    'cookie_consent_dialog_title': {
        'default': LazyI18nString.from_gettext(gettext_noop('Privacy settings')),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('Dialog title'),
            widget=I18nTextInput,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_settings-cookie_consent'}},
        )
    },
    'cookie_consent_dialog_button_yes': {
        'default': LazyI18nString.from_gettext(gettext_noop('Accept all cookies')),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('"Accept" button description'),
            widget=I18nTextInput,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_settings-cookie_consent'}},
        )
    },
    'cookie_consent_dialog_button_no': {
        'default': LazyI18nString.from_gettext(gettext_noop('Required cookies only')),
        'type': LazyI18nString,
        'serializer_class': I18nField,
        'form_class': I18nFormField,
        'form_kwargs': dict(
            label=_('"Reject" button description'),
            widget=I18nTextInput,
            widget_kwargs={'attrs': {'data-display-dependency': '#id_settings-cookie_consent'}},
        )
    },
    'seating_choice': {
        'default': 'True',
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Customers can choose their own seats"),
            help_text=_("If disabled, you will need to manually assign seats in the backend. Note that this can mean "
                        "people will not know their seat after their purchase and it might not be written on their "
                        "ticket."),
        ),
        'type': bool,
    },
    'seating_minimal_distance': {
        'default': '0',
        'type': float
    },
    'seating_allow_blocked_seats_for_channel': {
        'default': [],
        'type': list
    },
    'seating_distance_within_row': {
        'default': 'False',
        'type': bool
    },
    'checkout_show_copy_answers_button': {
        'default': 'True',
        'type': bool,
        'form_class': forms.BooleanField,
        'serializer_class': serializers.BooleanField,
        'form_kwargs': dict(
            label=_("Show button to copy user input from other products"),
        ),
    }
}
SETTINGS_AFFECTING_CSS = {
    'primary_color', 'theme_color_success', 'theme_color_danger', 'primary_font',
    'theme_color_background', 'theme_round_borders'
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
        'Sir',
    ))),
    ('german_common', (_('Most common German titles'), (
        'Dr.',
        'Prof.',
        'Prof. Dr.',
    ))),
    ('dr_prof_he', ('Dr., Prof., H.E.', (
        'Dr.',
        'Prof.',
        'H.E.',
    )))
])

PERSON_NAME_SALUTATIONS = [
    ("Ms", pgettext_lazy("person_name_salutation", "Ms")),
    ("Mr", pgettext_lazy("person_name_salutation", "Mr")),
    ("Mx", pgettext_lazy("person_name_salutation", "Mx")),
]


def concatenation_for_salutation(d):
    salutation = d.get("salutation")
    title = d.get("title")
    given_name = d.get("given_name")
    family_name = d.get("family_name")
    # degree (after name) is not used in salutation
    # see https://www.schreibwerkstatt.co.at/2012/12/25/der-umgang-mit-akademischen-graden/

    if salutation == "Mx":
        salutation = None
    elif salutation:
        salutation = pgettext("person_name_salutation", salutation)
        given_name = None

    return " ".join(filter(None, (salutation, title, given_name, family_name)))


def get_name_parts_localized(name_parts, key):
    value = name_parts.get(key, "")
    if key == "salutation" and value:
        return pgettext_lazy("person_name_salutation", value)
    return value


PERSON_NAME_SCHEMES = OrderedDict([
    ('given_family', {
        'fields': (
            # field_name, label, weight for widget width
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
        'concatenation_all_components': lambda d: str(d.get('full_name', '')) + " (\"" + d.get('calling_name', '') + "\")",
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
        'concatenation_all_components': lambda d: str(d.get('full_name', '')) + " (" + d.get('latin_transcription', '') + ")",
        'sample': {
            'full_name': '庄司',
            'latin_transcription': 'Shōji',
            '_scheme': 'full_transcription',
        },
    }),
    ('salutation_given_family', {
        'fields': (
            ('salutation', pgettext_lazy('person_name', 'Salutation'), 1),
            ('given_name', _('Given name'), 2),
            ('family_name', _('Family name'), 2),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in (d.get(key, '') for key in ["given_name", "family_name"]) if p
        ),
        'concatenation_for_salutation': concatenation_for_salutation,
        'concatenation_all_components': lambda d: ' '.join(
            str(p) for p in (get_name_parts_localized(d, key) for key in ["salutation", "given_name", "family_name"]) if p
        ),
        'sample': {
            'salutation': pgettext_lazy('person_name_sample', 'Mr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'salutation_given_family',
        },
    }),
    ('salutation_title_given_family', {
        'fields': (
            ('salutation', pgettext_lazy('person_name', 'Salutation'), 1),
            ('title', pgettext_lazy('person_name', 'Title'), 1),
            ('given_name', _('Given name'), 2),
            ('family_name', _('Family name'), 2),
        ),
        'concatenation': lambda d: ' '.join(
            str(p) for p in (d.get(key, '') for key in ["title", "given_name", "family_name"]) if p
        ),
        'concatenation_for_salutation': concatenation_for_salutation,
        'concatenation_all_components': lambda d: ' '.join(
            str(p) for p in (get_name_parts_localized(d, key) for key in ["salutation", "title", "given_name", "family_name"]) if p
        ),
        'sample': {
            'salutation': pgettext_lazy('person_name_sample', 'Mr'),
            'title': pgettext_lazy('person_name_sample', 'Dr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            '_scheme': 'salutation_title_given_family',
        },
    }),
    ('salutation_title_given_family_degree', {
        'fields': (
            ('salutation', pgettext_lazy('person_name', 'Salutation'), 1),
            ('title', pgettext_lazy('person_name', 'Title'), 1),
            ('given_name', _('Given name'), 2),
            ('family_name', _('Family name'), 2),
            ('degree', pgettext_lazy('person_name', 'Degree (after name)'), 2),
        ),
        'concatenation': lambda d: (
            ' '.join(
                str(p) for p in (d.get(key, '') for key in ["title", "given_name", "family_name"]) if p
            ) +
            str((', ' if d.get('degree') else '')) +
            str(d.get('degree', ''))
        ),
        'concatenation_for_salutation': concatenation_for_salutation,
        'concatenation_all_components': lambda d: (
            ' '.join(
                str(p) for p in (get_name_parts_localized(d, key) for key in ["salutation", "title", "given_name", "family_name"]) if p
            ) +
            str((', ' if d.get('degree') else '')) +
            str(d.get('degree', ''))
        ),
        'sample': {
            'salutation': pgettext_lazy('person_name_sample', 'Mr'),
            'title': pgettext_lazy('person_name_sample', 'Dr'),
            'given_name': pgettext_lazy('person_name_sample', 'John'),
            'family_name': pgettext_lazy('person_name_sample', 'Doe'),
            'degree': pgettext_lazy('person_name_sample', 'MA'),
            '_scheme': 'salutation_title_given_family_degree',
        },
    }),
])

DEFAULTS['name_scheme']['serializer_kwargs']['choices'] = ((k, k) for k in PERSON_NAME_SCHEMES)

COUNTRIES_WITH_STATE_IN_ADDRESS = {
    # Source: http://www.bitboost.com/ref/international-address-formats.html
    # This is not a list of countries that *have* states, this is a list of countries where states
    # are actually *used* in postal addresses. This is obviously not complete and opinionated.
    # Country: [(List of subdivision types as defined by pycountry), (short or long form to be used)]
    'AU': (['State', 'Territory'], 'short'),
    'BR': (['State'], 'short'),
    'CA': (['Province', 'Territory'], 'short'),
    # 'CN': (['Province', 'Autonomous region', 'Munincipality'], 'long'),
    'MY': (['State'], 'long'),
    'MX': (['State', 'Federal district'], 'short'),
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
settings_hierarkey.add_type(LazyI18nStringList,
                            serialize=operator.methodcaller("serialize"),
                            unserialize=LazyI18nStringList.unserialize)
settings_hierarkey.add_type(RelativeDateWrapper,
                            serialize=lambda rdw: rdw.to_string(),
                            unserialize=lambda s: RelativeDateWrapper.from_string(s))
settings_hierarkey.add_type(PhoneNumber, lambda pn: pn.as_international, lambda s: parse(s) if s else None)


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

    def get(self, key: str, default: Any = None, as_type: type = str, binary_file: bool = False):
        return self._event.settings.get(
            self._convert_key(key), default=default, as_type=as_type, binary_file=binary_file
        )

    def set(self, key: str, value: Any):
        self._event.settings.set(self._convert_key(key), value)


def validate_event_settings(event, settings_dict):
    from pretix.base.models import Event
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

    if isinstance(event, Event):
        validate_event_settings.send(sender=event, settings_dict=settings_dict)


def validate_organizer_settings(organizer, settings_dict):
    # This is not doing anything for the time being.
    # But earlier we called validate_event_settings for the organizer, too - and that didn't do anything for
    # organizer-settings either.
    if settings_dict.get('reusable_media_type_nfc_mf0aes') and settings_dict.get('reusable_media_type_nfc_uid'):
        raise ValidationError({
            'reusable_media_type_nfc_uid': _('This needs to be disabled if other NFC-based types are active.')
        })


def global_settings_object(holder):
    if not hasattr(holder, '_global_settings_object'):
        holder._global_settings_object = GlobalSettingsObject()
    return holder._global_settings_object
