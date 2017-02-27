import decimal
import json
from datetime import date, datetime, time

from django.core.cache import cache
from typing import Any, Dict, Optional

import dateutil.parser
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db.models import Model
from django.utils.translation import ugettext_noop

from i18nfield.strings import LazyI18nString
from pretix.base.models.settings import GlobalSetting

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
    'invoice_address_asked': {
        'default': 'True',
        'type': bool,
    },
    'invoice_address_required': {
        'default': 'False',
        'type': bool,
    },
    'invoice_address_vatid': {
        'default': 'False',
        'type': bool,
    },
    'invoice_numbers_consecutive': {
        'default': 'True',
        'type': bool,
    },
    'reservation_time': {
        'default': '30',
        'type': int
    },
    'payment_term_days': {
        'default': '14',
        'type': int
    },
    'payment_term_last': {
        'default': None,
        'type': datetime,
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
        'default': '0.00',
        'type': decimal.Decimal
    },
    'invoice_generate': {
        'default': 'False',
        'type': str
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
        'type': datetime
    },
    'last_order_modification_date': {
        'default': None,
        'type': datetime
    },
    'cancel_allow_user': {
        'default': 'True',
        'type': bool
    },
    'contact_mail': {
        'default': None,
        'type': str
    },
    'imprint_url': {
        'default': None,
        'type': str
    },
    'mail_prefix': {
        'default': None,
        'type': str
    },
    'mail_from': {
        'default': settings.MAIL_FROM,
        'type': str
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

we successfully received your order for {event}. As you only ordered
free products, no payment is required.

You can change your order details and view the status of your order at
{url}

Best regards,
Your {event} team"""))
    },
    'mail_text_order_placed': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

we successfully received your order for {event} with a total value
of {total} {currency}. Please complete your payment before {date}.

{paymentinfo}

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

we did not yet receive a payment for your order for {event}.
Please keep in mind that if we only guarantee your order if we receive
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
    'presale_css_file': {
        'default': None,
        'type': str
    },
    'presale_css_checksum': {
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
    }
}


class SettingsProxy:
    """
    This object allows convenient access to settings stored in the
    EventSettings/OrganizerSettings database model. It exposes all settings as
    properties and it will do all the nasty inheritance and defaults stuff for
    you.
    """

    def __init__(self, obj: Model, parent: Optional[Model]=None, type=None):
        self._obj = obj
        self._parent = parent
        self._cached_obj = None
        self._write_cached_obj = None
        self._type = type

    def _cache(self) -> Dict[str, Any]:
        if self._cached_obj is None:
            self._cached_obj = cache.get_or_set(
                'settings_{}_{}'.format(self._obj.settings_namespace, self._obj.pk),
                lambda: {s.key: s.value for s in self._obj.setting_objects.all()},
                timeout=1800
            )
        return self._cached_obj

    def _write_cache(self) -> Dict[str, Any]:
        if self._write_cached_obj is None:
            self._write_cached_obj = {
                s.key: s for s in self._obj.setting_objects.all()
            }
        return self._write_cached_obj

    def _flush(self) -> None:
        self._cached_obj = None
        self._write_cached_obj = None
        self._flush_external_cache()

    def _flush_external_cache(self):
        cache.delete('settings_{}_{}'.format(self._obj.settings_namespace, self._obj.pk))

    def freeze(self) -> dict:
        """
        Returns a dictionary of all settings set for this object, including
        any default values of its parents or hardcoded in pretix.
        """
        settings = {}
        for key, v in DEFAULTS.items():
            settings[key] = self._unserialize(v['default'], v['type'])
        if self._parent:
            settings.update(self._parent.settings.freeze())
        for key in self._cache():
            settings[key] = self.get(key)
        return settings

    def _unserialize(self, value: str, as_type: type, binary_file=False) -> Any:
        if as_type is None and value is not None and value.startswith('file://'):
            as_type = File

        if as_type is not None and isinstance(value, as_type):
            return value
        elif value is None:
            return None
        elif as_type == int or as_type == float or as_type == decimal.Decimal:
            return as_type(value)
        elif as_type == dict or as_type == list:
            return json.loads(value)
        elif as_type == bool or value in ('True', 'False'):
            return value == 'True'
        elif as_type == File:
            try:
                fi = default_storage.open(value[7:], 'rb' if binary_file else 'r')
                fi.url = default_storage.url(value[7:])
                return fi
            except OSError:
                return False
        elif as_type == datetime:
            return dateutil.parser.parse(value)
        elif as_type == date:
            return dateutil.parser.parse(value).date()
        elif as_type == time:
            return dateutil.parser.parse(value).time()
        elif as_type == LazyI18nString and not isinstance(value, LazyI18nString):
            try:
                return LazyI18nString(json.loads(value))
            except ValueError:
                return LazyI18nString(str(value))
        elif as_type is not None and issubclass(as_type, Model):
            return as_type.objects.get(pk=value)
        return value

    def _serialize(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        elif isinstance(value, int) or isinstance(value, float) \
                or isinstance(value, bool) or isinstance(value, decimal.Decimal):
            return str(value)
        elif isinstance(value, list) or isinstance(value, dict):
            return json.dumps(value)
        elif isinstance(value, datetime) or isinstance(value, date) or isinstance(value, time):
            return value.isoformat()
        elif isinstance(value, Model):
            return value.pk
        elif isinstance(value, LazyI18nString):
            return json.dumps(value.data)
        elif isinstance(value, File):
            return 'file://' + value.name

        raise TypeError('Unable to serialize %s into a setting.' % str(type(value)))

    def get(self, key: str, default=None, as_type: type=None, binary_file=False):
        """
        Get a setting specified by key ``key``. Normally, settings are strings, but
        if you put non-strings into the settings object, you can request unserialization
        by specifying ``as_type``. If the key does not have a harcdoded type in the pretix source,
        omitting ``as_type`` always will get you a string.

        If the setting with the specified name does not exist on this object, any parent object
        will be queried (e.g. the organizer of an event). If still no value is found, a default
        value hardcoded will be returned if one exists. If not, the value of the ``default`` argument
        will be returned instead.
        """
        if as_type is None and key in DEFAULTS:
            as_type = DEFAULTS[key]['type']

        if key in self._cache():
            value = self._cache()[key]
        else:
            value = None
            if self._parent:
                value = self._parent.settings.get(key, as_type=str)
            if value is None and key in DEFAULTS:
                value = DEFAULTS[key]['default']
            if value is None and default is not None:
                value = default

        return self._unserialize(value, as_type, binary_file=binary_file)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __getattr__(self, key: str) -> Any:
        if key.startswith('_'):
            return super().__getattr__(key)
        return self.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith('_'):
            return super().__setattr__(key, value)
        self.set(key, value)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def set(self, key: str, value: Any) -> None:
        """
        Stores a setting to the database of its object.
        """
        wc = self._write_cache()
        if key in wc:
            s = wc[key]
        else:
            s = self._type(object=self._obj, key=key)
        s.value = self._serialize(value)
        s.save()
        self._cache()[key] = s.value
        wc[key] = s
        self._flush_external_cache()

    def __delattr__(self, key: str) -> None:
        if key.startswith('_'):
            return super().__delattr__(key)
        self.delete(key)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def delete(self, key: str) -> None:
        """
        Deletes a setting from this object's storage.
        """
        if key in self._write_cache():
            self._write_cache()[key].delete()
            del self._write_cache()[key]

        if key in self._cache():
            del self._cache()[key]

        self._flush_external_cache()


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


class GlobalSettingsObject():
    settings_namespace = 'global'

    def __init__(self):
        self.settings = SettingsProxy(self, type=GlobalSetting)
        self.setting_objects = GlobalSetting.objects
        self.slug = '_global'
        self.pk = '_global'
