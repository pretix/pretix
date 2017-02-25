import logging

import i18nfield.forms
from django import forms
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.forms.models import ModelFormMetaclass
from django.utils import six
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class BaseI18nModelForm(i18nfield.forms.BaseI18nModelForm):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nModelForm(six.with_metaclass(ModelFormMetaclass, BaseI18nModelForm)):
    pass


class I18nFormSet(i18nfield.forms.I18nModelFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


class I18nInlineFormSet(i18nfield.forms.I18nInlineFormSet):
    # compatibility shim for django-i18nfield library

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        if event:
            kwargs['locales'] = event.settings.get('locales')
        super().__init__(*args, **kwargs)


class SettingsForm(i18nfield.forms.I18nForm):
    """
    This form is meant to be used for modifying EventSettings or OrganizerSettings. It takes
    care of loading the current values of the fields and saving the field inputs to the
    settings storage. It also deals with setting the available languages for internationalized
    fields.

    :param obj: The event or organizer object which should be used for the settings storage
    """

    BOOL_CHOICES = (
        ('False', _('disabled')),
        ('True', _('enabled')),
    )

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop('obj', None)
        self.locales = kwargs.pop('locales', None)
        kwargs['locales'] = self.obj.settings.get('locales') if self.obj else self.locales
        kwargs['initial'] = self.obj.settings.freeze()
        super().__init__(*args, **kwargs)

    def save(self):
        """
        Performs the save operation
        """
        for name, field in self.fields.items():
            value = self.cleaned_data[name]
            if isinstance(value, UploadedFile):
                # Delete old file
                fname = self.obj.settings.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.error('Deleting file %s failed.' % fname.name)

                # Create new file
                nonce = get_random_string(length=8)
                if isinstance(self.obj, Event):
                    fname = '%s/%s/%s.%s.%s' % (
                        self.obj.organizer.slug, self.obj.slug, name, nonce, value.name.split('.')[-1]
                    )
                else:
                    fname = '%s/%s.%s.%s' % (self.obj.slug, name, nonce, value.name.split('.')[-1])
                newname = default_storage.save(fname, value)
                value._name = newname
                self.obj.settings.set(name, value)
            elif isinstance(value, File):
                # file is unchanged
                continue
            elif isinstance(field, forms.FileField):
                # file is deleted
                fname = self.obj.settings.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.error('Deleting file %s failed.' % fname.name)
                del self.obj.settings[name]
            elif value is None:
                del self.obj.settings[name]
            elif self.obj.settings.get(name, as_type=type(value)) != value:
                self.obj.settings.set(name, value)
