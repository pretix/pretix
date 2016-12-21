from django.db import models


class Checkin(models.Model):
    """
    A checkin object is created when a person enters the event.
    """
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='checkins')
    datetime = models.DateTimeField(auto_now_add=True)
