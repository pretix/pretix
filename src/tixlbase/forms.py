from django.forms.models import ModelFormMetaclass, BaseModelForm
from django.utils import six
from versions.models import Versionable


class VersionedBaseModelForm(BaseModelForm):
    def save(self, commit=True):
        if self.instance.pk is not None and isinstance(self.instance, Versionable):
            if self.has_changed():
                self.instance = self.instance.clone()
        super().save(commit)


class VersionedModelForm(six.with_metaclass(ModelFormMetaclass, VersionedBaseModelForm)):
    pass
