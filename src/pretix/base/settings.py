from datetime import datetime, date, time
import json
import decimal

import dateutil.parser
from django.db.models import Model
from django.conf import settings
from versions.models import Versionable


DEFAULTS = {
    'user_mail_required': {
        'default': 'False',
        'type': bool
    },
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
    'timezone': {
        'default': settings.TIME_ZONE,
        'type': str
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
        'default': 'True',
        'type': bool
    },
    'last_order_modification_date': {
        'default': None,
        'type': datetime
    },
    'mail_from': {
        'default': settings.MAIL_FROM,
        'type': str
    }
}


class SettingsProxy:
    """
    This objects allows convenient access to settings stored in the
    EventSettings/OrganizerSettings database model. It exposes all settings as
    properties and it will do all the nasty inheritance and defaults stuff for
    you. It will return None for non-existing properties.
    """

    def __init__(self, obj, parent=None, type=None):
        self._obj = obj
        self._parent = parent
        self._cached_obj = None
        self._type = type

    def _cache(self):
        if self._cached_obj is None:
            self._cached_obj = {}
            for setting in self._obj.setting_objects.current.all():
                self._cached_obj[setting.key] = setting
        return self._cached_obj

    def _flush(self):
        self._cached_obj = None

    def _unserialize(self, value, as_type):
        if isinstance(value, as_type):
            return value
        elif value is None:
            return None
        elif as_type == int or as_type == float or as_type == decimal.Decimal:
            return as_type(value)
        elif as_type == dict or as_type == list:
            return json.loads(value)
        elif as_type == bool:
            return value == 'True'
        elif as_type == datetime:
            return dateutil.parser.parse(value)
        elif as_type == date:
            return dateutil.parser.parse(value).date()
        elif as_type == time:
            return dateutil.parser.parse(value).time()
        elif issubclass(as_type, Versionable):
            return as_type.objects.current.get(identity=value)
        elif issubclass(as_type, Model):
            return as_type.objects.get(pk=value)
        return value

    def _serialize(self, value):
        if isinstance(value, str):
            return value
        elif isinstance(value, int) or isinstance(value, float) \
                or isinstance(value, bool) or isinstance(value, decimal.Decimal):
            return str(value)
        elif isinstance(value, list) or isinstance(value, dict):
            return json.dumps(value)
        elif isinstance(value, datetime) or isinstance(value, date) or isinstance(value, time):
            return value.isoformat()
        elif isinstance(value, Versionable):
            return value.identity
        elif isinstance(value, Model):
            return value.pk

        raise TypeError('Unable to serialize %s into a setting.' % str(type(value)))

    def get(self, key, default=None, as_type=None):
        """
        Get a setting specified by key 'key'. Normally, settings are strings, but
        if you put non-strings into the settings object, you can request unserialization
        by specifying 'as_type'
        """
        if as_type is None and key in DEFAULTS:
            as_type = DEFAULTS[key]['type']
        elif as_type is None:
            as_type = str

        if key in self._cache():
            return self._unserialize(self._cache()[key].value, as_type)
        value = None
        if self._parent:
            value = self._parent.settings.get(key)
        if value is None and key in DEFAULTS:
            return self._unserialize(DEFAULTS[key]['default'], as_type)
        if value is None and default is not None:
            return self._unserialize(default, as_type)
        return self._unserialize(value, as_type)

    def __getitem__(self, key):
        return self.get(key)

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        if key.startswith('_'):
            return super().__setattr__(key, value)
        self.set(key, value)

    def __setitem__(self, key, value):
        self.set(key, value)

    def set(self, key, value):
        if key in self._cache():
            s = self._cache()[key]
            s = s.clone()
        else:
            s = self._type(object=self._obj, key=key)
        s.value = self._serialize(value)
        s.save()
        self._cache()[key] = s

    def __delattr__(self, key):
        if key.startswith('_'):
            return super().__delattr__(key)
        return self.__delitem__(key)

    def __delitem__(self, key):
        if key in self._cache():
            self._cache()[key].delete()
            del self._cache()[key]


class SettingsSandbox:
    """
    Transparently proxied access to event settings, handling your domain-
    prefixes for you.
    """

    def __init__(self, type, key, event):
        self._event = event
        self._type = type
        self._key = key

    def _convert_key(self, key):
        return '%s_%s_%s' % (self._type, self._key, key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __setattr__(self, key, value):
        if key.startswith('_'):
            return super().__setattr__(key, value)
        self.set(key, value)

    def __getattr__(self, item):
        return self.get(item)

    def __getitem__(self, item):
        return self.get(item)

    def __delitem__(self, key):
        del self._event.settings[self._convert_key(key)]

    def __delattr__(self, key):
        del self._event.settings[self._convert_key(key)]

    def get(self, key, default=None, as_type=str):
        return self._event.settings.get(self._convert_key(key), default=default, as_type=as_type)

    def set(self, key, value):
        self._event.settings.set(self._convert_key(key), value)
