import logging

import i18nfield.forms
from django.forms.models import ModelFormMetaclass
from django.utils import six
from django.utils.crypto import get_random_string
from hierarkey.forms import HierarkeyForm

from pretix.base.models import Event
from pretix.base.reldate import RelativeDateField, RelativeDateTimeField

from .validators import PlaceholderValidator  # NOQA

logger = logging.getLogger(__name__)


class BaseI18nModelForm(i18nfield.forms.BaseI18nModelForm):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        if self.event:
            kwargs['locales'] = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nModelForm(six.with_metaclass(ModelFormMetaclass, BaseI18nModelForm)):
    pass


class I18nFormSet(i18nfield.forms.I18nModelFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        if self.event:
            kwargs['locales'] = self.event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nInlineFormSet(i18nfield.forms.I18nInlineFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


class SettingsForm(i18nfield.forms.I18nFormMixin, HierarkeyForm):

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.get('obj', None)
        self.locales = self.obj.settings.get('locales') if self.obj else kwargs.pop('locales', None)
        kwargs['attribute_name'] = 'settings'
        kwargs['locales'] = self.locales
        kwargs['initial'] = self.obj.settings.freeze()
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if isinstance(f, (RelativeDateTimeField, RelativeDateField)):
                f.set_event(self.obj)

    def get_new_filename(self, name: str) -> str:
        nonce = get_random_string(length=8)
        if isinstance(self.obj, Event):
            fname = '%s/%s/%s.%s.%s' % (
                self.obj.organizer.slug, self.obj.slug, name, nonce, name.split('.')[-1]
            )
        else:
            fname = '%s/%s.%s.%s' % (self.obj.slug, name, nonce, name.split('.')[-1])
        return fname
