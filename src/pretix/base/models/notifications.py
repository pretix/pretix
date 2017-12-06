from django.db import models
from django.utils.translation import ugettext_lazy as _


class NotificationSetting(models.Model):
    """
    Stores that a user wants to get notifications of a certain type via a certain
    method for a certain event. If event is None, the notification shall be sent
    for all events the user has access to.

    :param user: The user to nofify.
    :type user: User
    :param action_type: The type of action to notify for.
    :type action_type: str
    :param event: The event to notify for.
    :type event: Event
    :param method: The method to notify with.
    :type method: str
    """
    CHANNELS = (
        ('mail', _('E-mail')),
    )
    user = models.ForeignKey('User', on_delete=models.CASCADE,
                             related_name='notification_settings')
    action_type = models.CharField(max_length=255)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.CASCADE,
                              related_name='notification_settings')
    method = models.CharField(max_length=255, choices=CHANNELS)

    class Meta:
        unique_together = ('user', 'action_type', 'event', 'method')
