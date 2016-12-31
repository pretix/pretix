from django.db import models
from django.utils.timezone import now


class Checkin(models.Model):
    """
    A checkin object is created when a person enters the event.
    """
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins')
    datetime = models.DateTimeField(default=now)
