import decimal
import json
from datetime import date, datetime, time

import dateutil.parser
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db.models import Model
from django.utils.translation import ugettext_noop
from typing import Any, Dict, Optional

from pretix.base.i18n import LazyI18nString

DEFAULTS = {
    'max_items_per_order': {
        'default': '10',
        'type': int
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
    'payment_term_accept_late': {
        'default': 'True',
        'type': bool
    },
    'presale_start_show_date': {
        'default': 'True',
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
    'mail_text_order_paid': {
        'type': LazyI18nString,
        'default': LazyI18nString.from_gettext(ugettext_noop("""Hello,

we successfully received your payment for {event}. Thank you!

You can change your order details and view the status of your order at
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
}


class SettingsProxy:
    """
    This objects allows convenient access to settings stored in the
    EventSettings/OrganizerSettings database model. It exposes all settings as
    properties and it will do all the nasty inheritance and defaults stuff for
    you. It will return None for non-existing properties.
    """

    def __init__(self, obj: Model, parent: Optional[Model]=None, type=None):
        self._obj = obj
        self._parent = parent
        self._cached_obj = None
        self._type = type

    def _cache(self) -> Dict[str, Any]:
        if self._cached_obj is None:
            self._cached_obj = {}
            for setting in self._obj.setting_objects.all():
                self._cached_obj[setting.key] = setting
        return self._cached_obj

    def _flush(self) -> None:
        self._cached_obj = None

    def freeze(self):
        settings = {}
        for key, v in DEFAULTS.items():
            settings[key] = self._unserialize(v['default'], v['type'])
        if self._parent:
            settings.update(self._parent.settings.freeze())
        for key, value in self._cache().items():
            settings[key] = self.get(key)
        return settings

    def _unserialize(self, value: str, as_type: type) -> Any:
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
                fi = default_storage.open(value[7:], 'r')
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

    def get(self, key: str, default: Any=None, as_type: type=None):
        """
        Get a setting specified by key 'key'. Normally, settings are strings, but
        if you put non-strings into the settings object, you can request unserialization
        by specifying 'as_type'
        """
        if as_type is None and key in DEFAULTS:
            as_type = DEFAULTS[key]['type']

        if key in self._cache():
            value = self._cache()[key].value
        else:
            value = None
            if self._parent:
                value = self._parent.settings.get(key)
            if value is None and key in DEFAULTS:
                value = DEFAULTS[key]['default']
            if value is None and default is not None:
                value = default

        return self._unserialize(value, as_type)

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
        if key in self._cache():
            s = self._cache()[key]
        else:
            s = self._type(object=self._obj, key=key)
        s.value = self._serialize(value)
        s.save()
        self._cache()[key] = s

    def __delattr__(self, key: str) -> None:
        if key.startswith('_'):
            return super().__delattr__(key)
        return self.__delitem__(key)

    def __delitem__(self, key: str) -> None:
        if key in self._cache():
            self._cache()[key].delete()
            del self._cache()[key]


class SettingsSandbox:
    """
    Transparently proxied access to event settings, handling your domain-
    prefixes for you.
    """

    def __init__(self, type: str, key: str, event: Model):
        self._event = event
        self._type = type
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
