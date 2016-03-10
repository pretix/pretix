import copy
import logging
import os

from django import forms
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.forms.models import BaseModelForm, ModelFormMetaclass
from django.utils import six
from django.utils.translation import ugettext_lazy as _

from pretix.base.i18n import I18nFormField
from pretix.base.models import Event

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class BaseI18nModelForm(BaseModelForm):
    """
    This is a helperclass to construct I18nModelForm
    """
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)
        if event:
            for k, field in self.fields.items():
                if isinstance(field, I18nFormField):
                    field.widget.enabled_langcodes = event.settings.get('locales')


class I18nModelForm(six.with_metaclass(ModelFormMetaclass, BaseI18nModelForm)):
    """
    This is a modified version of Django's ModelForm which differs from ModelForm in
    only one way: The constructor takes one additional optional argument ``event``
    which may be given an :pyclass:`pretix.base.models.Event` instance. If given, this
    instance is used to select the visible languages in all I18nFormFields of the form. If
    not given, all languages will be displayed.
    """
    pass


class SettingsForm(forms.Form):
    """
    This form is meant to be used for modifying Event- or OrganizerSettings
    """
    BOOL_CHOICES = (
        ('False', _('disabled')),
        ('True', _('enabled')),
    )

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop('obj')
        kwargs['initial'] = self.obj.settings.freeze()
        super().__init__(*args, **kwargs)
        for k, field in self.fields.items():
            if isinstance(field, I18nFormField):
                field.widget.enabled_langcodes = self.obj.settings.get('locales')

    def save(self):
        for name, field in self.fields.items():
            value = self.cleaned_data[name]
            if isinstance(value, UploadedFile):
                if isinstance(self.obj, Event):
                    fname = '%s/%s/%s.%s' % (
                        self.obj.organizer.slug, self.obj.slug, name, value.name.split('.')[-1]
                    )
                else:
                    fname = '%s/%s.%s' % (self.obj.slug, name, value.name.split('.')[-1])
                if not os.path.exists(os.path.dirname(fname)):
                    os.makedirs(os.path.dirname(fname))
                with default_storage.open(fname, 'wb+') as destination:
                    for chunk in value.chunks():
                        destination.write(chunk)
                value._name = fname
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

            if value is None:
                del self.obj.settings[name]
            elif self.obj.settings.get(name, as_type=type(value)) != value:
                self.obj.settings.set(name, value)
