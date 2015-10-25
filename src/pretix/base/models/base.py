import copy
import uuid
from datetime import datetime

import six
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from versions.models import Versionable as BaseVersionable, get_utc_now


class Versionable(BaseVersionable):
    class Meta:
        abstract = True

    def clone_shallow(self, forced_version_date: datetime=None):
        """
        This behaves like clone(), but misses all the Many2Many-relation-handling. This is
        a performance optimization for cases in which we have to handle the Many2Many relations
        by hand anyways.
        """
        if not self.pk:  # NOQA
            raise ValueError('Instance must be saved before it can be cloned')

        if self.version_end_date:  # NOQA
            raise ValueError('This is a historical item and can not be cloned.')

        if forced_version_date:  # NOQA
            if not self.version_start_date <= forced_version_date <= get_utc_now():
                raise ValueError('The clone date must be between the version start date and now.')
        else:
            forced_version_date = get_utc_now()

        earlier_version = self

        later_version = copy.copy(earlier_version)
        later_version.version_end_date = None
        later_version.version_start_date = forced_version_date

        # set earlier_version's ID to a new UUID so the clone (later_version) can
        # get the old one -- this allows 'head' to always have the original
        # id allowing us to get at all historic foreign key relationships
        earlier_version.id = six.u(str(uuid.uuid4()))
        earlier_version.version_end_date = forced_version_date
        earlier_version.save()

        for field in earlier_version._meta.many_to_many:
            earlier_version.clone_relations_shallow(later_version, field.attname, forced_version_date)

        if hasattr(earlier_version._meta, 'many_to_many_related'):
            for rel in earlier_version._meta.many_to_many_related:
                earlier_version.clone_relations_shallow(later_version, rel.via_field_name, forced_version_date)

        later_version.save()

        return later_version

    def clone_relations_shallow(self, clone, manager_field_name, forced_version_date):
        # Source: the original object, where relations are currently pointing to
        source = getattr(self, manager_field_name)  # returns a VersionedRelatedManager instance
        # Destination: the clone, where the cloned relations should point to
        source.through.objects.filter(**{source.source_field.attname: clone.id}).update(**{
            source.source_field.attname: self.id, 'version_end_date': forced_version_date
        })


def cachedfile_name(instance, filename: str) -> str:
    return 'cachedfiles/%s.%s' % (instance.id, filename.split('.')[-1])


class CachedFile(models.Model):
    """
    A cached file (e.g. pre-generated ticket PDF)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    expires = models.DateTimeField(null=True, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    filename = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedfile_name)


@receiver(post_delete, sender=CachedFile)
def cached_file_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)
