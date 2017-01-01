import logging

from django import forms
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.forms.models import (
    BaseInlineFormSet, BaseModelForm, BaseModelFormSet, ModelFormMetaclass,
)
from django.utils import six
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _

from pretix.base.i18n import I18nFormField
from pretix.base.models import Event

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class BaseI18nModelForm(BaseModelForm):
    """
    This is a helperclass to construct an I18nModelForm.
    """
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        locales = kwargs.pop('locales', None)
        super().__init__(*args, **kwargs)
        if event or locales:
            for k, field in self.fields.items():
                if isinstance(field, I18nFormField):
                    field.widget.enabled_langcodes = event.settings.get('locales') if event else locales


class I18nModelForm(six.with_metaclass(ModelFormMetaclass, BaseI18nModelForm)):
    """
    This is a modified version of Django's ModelForm which differs from ModelForm in
    only one way: The constructor takes one additional optional argument ``event``
    expecting an `Event` instance. If given, this instance is used to select
    the visible languages in all I18nFormFields of the form. If not given, all languages
    will be displayed.
    """
    pass


class I18nFormSet(BaseModelFormSet):
    """
    This is equivalent to a normal BaseModelFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)

    @property
    def empty_form(self):
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix('__prefix__'),
            empty_permitted=True,
            event=self.event
        )
        self.add_fields(form, None)
        return form


class I18nInlineFormSet(BaseInlineFormSet):
    """
    This is equivalent to a normal BaseInlineFormset, but cares for the special needs
    of I18nForms (see there for more information).
    """

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['event'] = self.event
        return super()._construct_form(i, **kwargs)


class SettingsForm(forms.Form):
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
        kwargs['initial'] = self.obj.settings.freeze()
        super().__init__(*args, **kwargs)
        if self.obj or self.locales:
            for k, field in self.fields.items():
                if isinstance(field, I18nFormField):
                    field.widget.enabled_langcodes = self.obj.settings.get('locales') if self.obj else self.locales

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
