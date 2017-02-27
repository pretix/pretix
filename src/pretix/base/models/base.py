import json
import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.crypto import get_random_string
from i18nfield.utils import I18nJSONEncoder


def cachedfile_name(instance, filename: str) -> str:
    secret = get_random_string(length=12)
    return 'cachedfiles/%s.%s.%s' % (instance.id, secret, filename.split('.')[-1])


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


class LoggingMixin:

    def log_action(self, action, data=None, user=None):
        """
        Create a LogEntry object that is related to this object.
        See the LogEntry documentation for details.

        :param action: The namespaced action code
        :param data: Any JSON-serializable object
        :param user: The user performing the action (optional)
        """
        from .log import LogEntry
        from .event import Event

        event = None
        if isinstance(self, Event):
            event = self
        elif hasattr(self, 'event'):
            event = self.event
        l = LogEntry(content_object=self, user=user, action_type=action, event=event)
        if data:
            l.data = json.dumps(data, cls=I18nJSONEncoder)
        l.save()


class LoggedModel(models.Model, LoggingMixin):

    class Meta:
        abstract = True

    def all_logentries(self):
        """
        Returns all log entries that are attached to this object.

        :return: A QuerySet of LogEntry objects
        """
        from .log import LogEntry

        return LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(type(self)), object_id=self.pk
        ).select_related('user', 'event')
