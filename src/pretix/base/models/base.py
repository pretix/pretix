import json
import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property

from pretix.helpers.json import CustomJSONEncoder


def cachedfile_name(instance, filename: str) -> str:
    secret = get_random_string(length=12)
    return 'cachedfiles/%s.%s.%s' % (instance.id, secret, filename.split('.')[-1])


class CachedFile(models.Model):
    """
    An uploaded file, with an optional expiry date.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    expires = models.DateTimeField(null=True, blank=True)
    date = models.DateTimeField(null=True, blank=True)
    filename = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    file = models.FileField(null=True, blank=True, upload_to=cachedfile_name, max_length=255)


@receiver(post_delete, sender=CachedFile)
def cached_file_delete(sender, instance, **kwargs):
    if instance.file:
        # Pass false so FileField doesn't save the model.
        instance.file.delete(False)


class LoggingMixin:

    def log_action(self, action, data=None, user=None, api_token=None, auth=None, save=True):
        """
        Create a LogEntry object that is related to this object.
        See the LogEntry documentation for details.

        :param action: The namespaced action code
        :param data: Any JSON-serializable object
        :param user: The user performing the action (optional)
        """
        from pretix.api.models import OAuthAccessToken, OAuthApplication
        from pretix.api.webhooks import notify_webhooks
        from ..services.notifications import notify
        from .devices import Device
        from .event import Event
        from .log import LogEntry
        from .organizer import TeamAPIToken

        event = None
        if isinstance(self, Event):
            event = self
        elif hasattr(self, 'event'):
            event = self.event
        if user and not user.is_authenticated:
            user = None

        kwargs = {}
        if isinstance(auth, OAuthAccessToken):
            kwargs['oauth_application'] = auth.application
        elif isinstance(auth, OAuthApplication):
            kwargs['oauth_application'] = auth
        elif isinstance(auth, TeamAPIToken):
            kwargs['api_token'] = auth
        elif isinstance(auth, Device):
            kwargs['device'] = auth
        elif isinstance(api_token, TeamAPIToken):
            kwargs['api_token'] = api_token

        logentry = LogEntry(content_object=self, user=user, action_type=action, event=event, **kwargs)
        if isinstance(data, dict):
            sensitivekeys = ['password', 'secret', 'api_key']

            for sensitivekey in sensitivekeys:
                for k, v in data.items():
                    if (sensitivekey in k) and v:
                        data[k] = "********"

            logentry.data = json.dumps(data, cls=CustomJSONEncoder, sort_keys=True)
        elif data:
            raise TypeError("You should only supply dictionaries as log data.")
        if save:
            logentry.save()

            if logentry.notification_type:
                notify.apply_async(args=(logentry.pk,))
            if logentry.webhook_type:
                notify_webhooks.apply_async(args=(logentry.pk,))

        return logentry


class LoggedModel(models.Model, LoggingMixin):

    class Meta:
        abstract = True

    @cached_property
    def logs_content_type(self):
        return ContentType.objects.get_for_model(type(self))

    @cached_property
    def all_logentries_link(self):
        from pretix.base.models import Event

        if isinstance(self, Event):
            event = self
        elif hasattr(self, 'event'):
            event = self.event
        else:
            return None
        return reverse(
            'control:event.log',
            kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }
        ) + '?content_type={}&object={}'.format(
            self.logs_content_type.pk,
            self.pk
        )

    def top_logentries(self):
        qs = self.all_logentries()
        if self.all_logentries_link:
            qs = qs[:25]
        return qs

    def top_logentries_has_more(self):
        return self.all_logentries().count() > 25

    def all_logentries(self):
        """
        Returns all log entries that are attached to this object.

        :return: A QuerySet of LogEntry objects
        """
        from .log import LogEntry

        return LogEntry.objects.filter(
            content_type=self.logs_content_type, object_id=self.pk
        ).select_related('user', 'event', 'oauth_application', 'api_token', 'device')


class LockModel:
    def refresh_for_update(self, fields=None, using=None, **kwargs):
        """
        Like refresh_from_db(), but with select_for_update().
        See also https://code.djangoproject.com/ticket/28344
        """
        if fields is not None:
            if not fields:
                return
            if any(LOOKUP_SEP in f for f in fields):
                raise ValueError(
                    'Found "%s" in fields argument. Relations and transforms '
                    'are not allowed in fields.' % LOOKUP_SEP)

        hints = {'instance': self}
        db_instance_qs = self.__class__._base_manager.db_manager(using, hints=hints).filter(pk=self.pk).select_for_update(**kwargs)

        # Use provided fields, if not set then reload all non-deferred fields.
        deferred_fields = self.get_deferred_fields()
        if fields is not None:
            fields = list(fields)
            db_instance_qs = db_instance_qs.only(*fields)
        elif deferred_fields:
            fields = [f.attname for f in self._meta.concrete_fields
                      if f.attname not in deferred_fields]
            db_instance_qs = db_instance_qs.only(*fields)

        db_instance = db_instance_qs.get()
        non_loaded_fields = db_instance.get_deferred_fields()
        for field in self._meta.concrete_fields:
            if field.attname in non_loaded_fields:
                # This field wasn't refreshed - skip ahead.
                continue
            setattr(self, field.attname, getattr(db_instance, field.attname))
            # Clear cached foreign keys.
            if field.is_relation and field.is_cached(self):
                field.delete_cached_value(self)

        # Clear cached relations.
        for field in self._meta.related_objects:
            if field.is_cached(self):
                field.delete_cached_value(self)

        self._state.db = db_instance._state.db
