import logging
from collections import OrderedDict

from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, LogEntry
from pretix.base.signals import register_notification_types

logger = logging.getLogger(__name__)
_ALL_TYPES = None


class NotificationType:
    def __init__(self, event: Event = None):
        self.event = event

    def __str__(self):
        return self.action_types

    @property
    def action_type(self) -> str:
        """
        The action_type string that this notification handles, for example
        pretix.event.order.paid. Only one notification type should be registered
        per action type.
        """
        raise NotImplementedError()  # NOQA

    @property
    def verbose_name(self) -> str:
        """
        A human-readable name of this notification type.
        """
        raise NotImplementedError()  # NOQA

    @property
    def required_permission(self) -> str:
        """
        The permission a user needs to hold for the related event to receive this
        notification
        """
        raise NotImplementedError()  # NOQA

    def render_notification(self, logentry: LogEntry):
        return logentry.display()


def get_all_notification_types(event=None):
    global _ALL_TYPES

    if event is None and _ALL_TYPES:
        return _ALL_TYPES

    types = OrderedDict()
    for recv, ret in register_notification_types.send(event):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.action_type] = r
        else:
            types[ret.action_type] = ret
    if event is None:
        _ALL_TYPES = types
    return types


class ParametrizedOrderNotification(NotificationType):
    required_permission = "can_view_orders"

    def __init__(self, event, action_type, verbose_name):
        self._action_type = action_type
        self._verbose_name = verbose_name
        super().__init__(event)

    @property
    def action_type(self):
        return self._action_type

    @property
    def verbose_name(self):
        return self._verbose_name


@receiver(register_notification_types, dispatch_uid="base_register_default_notification_types")
def register_default_notification_types(sender, **kwargs):
    return (
        ParametrizedOrderNotification(sender, 'pretix.event.order.placed', _('New order placed')),
        ParametrizedOrderNotification(sender, 'pretix.event.order.paid', _('Order marked as paid')),
    )
