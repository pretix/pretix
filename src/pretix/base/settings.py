DEFAULTS = {
    'user_mail_required': 'False',
    'max_items_per_order': '10',
    'attendee_names_asked': 'True',
    'attendee_names_required': 'False',
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

    def get(self, key, default=None):
        if key in self._cache():
            return self._cache()[key].value
        value = None
        if self._parent:
            value = self._parent.settings.get(key)
        if value is None and key in DEFAULTS:
            return DEFAULTS[key]
        if value is None and default is not None:
            return default
        return value

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
        s.value = value
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

    def get(self, key, default=None):
        return self._event.settings.get(self._convert_key(key), default)

    def set(self, key, value):
        self._event.settings.set(self._convert_key(key), value)
