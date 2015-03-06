from django.forms.models import ModelFormMetaclass, BaseModelForm
from django import forms
from django.utils import six
from versions.models import Versionable


class VersionedBaseModelForm(BaseModelForm):
    """
    This is a helperclass to construct VersionedModelForm
    """
    def save(self, commit=True):
        if self.instance.pk is not None and isinstance(self.instance, Versionable):
            if self.has_changed():
                self.instance = self.instance.clone()
        return super().save(commit)


class VersionedModelForm(six.with_metaclass(ModelFormMetaclass, VersionedBaseModelForm)):
    """
    This is a modified version of Django's ModelForm which differs from ModelForm in
    only one way: It executes the .clone() method of an object before saving it back to
    the database, if the model is a sub-class of versions.models.Versionable. You can
    safely use this as a base class for all your model forms, it will work out correctly
    with both versioned and non-versioned models.
    """
    pass


class SettingsForm(forms.Form):
    """
    This form is meant to be used for modifying Event- or OrganizerSettings
    """

    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop('obj')
        if 'initial' not in kwargs:
            kwargs['initial'] = self.obj.settings
        super().__init__(*args, **kwargs)

    def save(self):
        for name, field in self.fields.items():
            value = self.cleaned_data[name]
            if value is None:
                del self.obj.settings[name]
            elif self.obj.settings.get(value, as_type=type(value)) != value:
                self.obj.settings.set(name, value)
