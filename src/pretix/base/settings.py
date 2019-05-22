import json
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.files import File
from django.db.models import Model
from django.utils.translation import (
    pgettext_lazy, ugettext_lazy as _, ugettext_noop,
)
from hierarkey.models import GlobalSettingsBase, Hierarkey
from i18nfield.strings import LazyI18nString

from pretix.base.models.tax import TaxRule
from pretix.base.reldate import RelativeDateWrapper

DEFAULTS = {
    'max_items_per_order': {
        'default': '10',
        'type': int
    },
    'display_net_prices': {
        'default': 'False',
        'type': bool
    },
    'attendee_names_asked': {
        'default': 'True',
        'type': bool
    },
    'attendee_names_required': {
        'default': 'False',
        'type': bool
    },
    'attendee_emails_asked': {
        'default': 'False',
        'type': bool
    },
    'attendee_emails_required': {
        'default': 'False',
        'type': bool
    },
    'order_email_asked_twice': {
        'default': 'False',
        'type': bool
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
    'invoice_numbers_consecutive': {
        'default': 'True',
        'type': bool,
    },
    'invoice_numbers_prefix': {
        'default': '',
        'type': str,
    },
    'invoice_renderer': {
        'default': 'classic',
        'type': str,
    },
    'reservation_time': {
        'default': '30',
        'type': int
    },
    'redirect_to_checkout_directly': {
        'default': 'False',
        'type': bool
    },
    'presale_has_ended_text': {
        'default': '',
        'type': LazyI18nString
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
    'payment_term_accept_late': {
        'default': 'True',
        'type': bool
    },
    'presale_start_show_date': {
        'default': 'True',
        'type': bool
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
        'type': bool
    },
    'timezone': {
        'default': settings.TIME_ZONE,
        'type': str
    },
    'locales': {
        'default': json.dumps([settings.LANGUAGE_CODE]),
        'type': list
    },
    'locale': {
        'default': settings.LANGUAGE_CODE,
        'type': str
    },
    'show_date_to': {
        'default': 'True',
        'type': bool
    },
    'show_times': {
        'default': 'True',
        'type': bool
    },
    'show_quota_left': {
        'default': 'False',
        'type': bool
    },
    'show_variations_expanded': {
        'default': 'False',
        'type': bool
    },
    'waiting_list_enabled': {
        'default': 'False',
        'type': bool
    },
    'waiting_list_auto': {
        'default': 'True',
        'type': bool
    },
    'waiting_list_hours': {
        'default': '48',
        'type': int
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
        'type': str
    },
    'imprint_url': {
        'default': None,
        'type': str
    },
    'confirm_text': {
        'default': None,
        'type': LazyI18nString
    },
    'mail_html_renderer': {
        'default': 'classic',
        'type': str
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
of {total_with_currency}. Please complete your payment before {date}.

{payment_info}

You can change your order details and view the status of your order at
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

Please continue by paying for your order before {date}.

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
        'type': str
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
    'invoice_logo_image': {
        'default': None,
        'type': File
    },
    'frontpage_text': {
        'default': '',
        'type': LazyI18nString
    },
    'voucher_explanation_text': {
        'default': '',
        'type': LazyI18nString
    },
    'organizer_info_text': {
        'default': '',
        'type': LazyI18nString
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
    'frontpage_subevent_ordering': {
        'default': 'date_ascending',
        'type': str
    },
    'name_scheme': {
        'default': 'full',
        'type': str
    }
}
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
