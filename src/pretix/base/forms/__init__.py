import copy
import logging

from django import forms
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.forms.models import BaseModelForm, ModelFormMetaclass
from django.utils import six
from django.utils.translation import ugettext_lazy as _
from versions.models import Versionable

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


class VersionedBaseModelForm(BaseI18nModelForm):
    """
    This is a helperclass to construct VersionedModelForm
    """
    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        self.original_instance = copy.copy(instance) if instance else None
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        if self.instance.pk is not None and isinstance(self.instance, Versionable):
            if self.has_changed() and self.original_instance:
                new = self.instance
                old = self.original_instance
                clone = old.clone()
                for f in type(self.instance)._meta.get_fields():
                    if f.name not in (
                            'id', 'identity', 'version_start_date', 'version_end_date',
                            'version_birth_date'
                    ) and not isinstance(f, (
                            models.ManyToOneRel, models.ManyToManyRel, models.ManyToManyField
                    )):
                        setattr(clone, f.name, getattr(new, f.name))
                self.instance = clone
        return super().save(commit)


class VersionedModelForm(six.with_metaclass(ModelFormMetaclass, VersionedBaseModelForm)):
    """
    This is a modified version of I18nModelForm which differs from I18nModelForm in
    only one way: It executes the .clone() method of an object before saving it back to
    the database, if the model is a sub-class of versions.models.Versionable. You can
    safely use this as a base class for all your model forms, it will work out correctly
    with both versioned and non-versioned models.
    """
    pass


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
        kwargs['initial'] = self.obj.settings
        super().__init__(*args, **kwargs)

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
