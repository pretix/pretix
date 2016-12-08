from django.db import models


class Checkin(models.Model):
    position = models.ForeignKey('pretixbase.OrderPosition', related_name='pretixdroid_checkins')
    datetime = models.DateTimeField(auto_now_add=True)
