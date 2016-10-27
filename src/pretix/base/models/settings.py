from django.db import models


class GlobalSetting(models.Model):
    """
    A global setting is a key-value setting which can be set for a
    pretix instance. It will be inherited by all events and organizers.
    It is filled via the register_global_settings signal.
    """
    key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()

    def __init__(self, *args, object=None, **kwargs):
        super().__init__(*args, **kwargs)


class OrganizerSetting(models.Model):
    """
    An organizer setting is a key-value setting which can be set for an
    organizer. It will be inherited by the events of this organizer
    """
    object = models.ForeignKey('Organizer', related_name='setting_objects', on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField()


class EventSetting(models.Model):
    """
    An event setting is a key-value setting which can be set for a
    specific event
    """
    object = models.ForeignKey('Event', related_name='setting_objects', on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField()
