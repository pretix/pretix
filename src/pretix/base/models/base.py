import uuid

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


def cachedfile_name(instance, filename: str) -> str:
    return 'cachedfiles/%012d.%s' % (instance.id, filename.split('.')[-1])


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


class LoggedModel(models.Model):
    logentries = GenericRelation('LogEntry')

    def log_action(self, user, action, data):
        from .log import LogEntry
        from .event import Event

        event = None
        if isinstance(self, Event):
            event = self
        elif hasattr(self, 'event'):
            event = self.event
        LogEntry.objects.create(content_object=self, user=user, action=action, data=data, event=event)

    class Meta:
        abstract = True
