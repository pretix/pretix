import logging
from collections import OrderedDict, namedtuple

from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, LogEntry
from pretix.base.signals import register_notification_types
from pretix.base.templatetags.money import money_filter
from pretix.helpers.urls import build_absolute_uri

logger = logging.getLogger(__name__)
_ALL_TYPES = None


NotificationAttribute = namedtuple('NotificationAttribute', ('title', 'value'))
NotificationAction = namedtuple('NotificationAction', ('label', 'url'))


class Notification:
    """
    Represents a notification that is sent/shown to a user. A notification consists of:

    * one ``event`` reference
    * one ``title`` text that is shown e.g. in the email subject or in a headline
    * optionally one ``detail`` text that may or may not be shown depending on the notification method
    * optionally one ``url`` that should be absolute and point to the context of an notification (e.g. an order)
    * optionally a number of attributes consisting of a title and a value that can be used to add additional details
      to the notification (e.g. "Customer: ABC")
    * optionally a number of actions that may or may not be shown as buttons depending on the notification method,
      each consisting of a button label and an absolute URL to point to.
    """

    def __init__(self, event: Event, title: str, detail: str=None, url: str=None):
        self.title = title
        self.event = event
        self.detail = detail
        self.url = url
        self.attributes = []
        self.actions = []

    def add_action(self, label, url):
        """
        Add an action to the notification, defined by a label and an url. An example could be a label of "View order"
        and an url linking to the order detail page.
        """
        self.actions.append(NotificationAction(label, url))

    def add_attribute(self, title, value):
        """
        Add an attribute to the notification, defined by a title and a value. An example could be a title of
        "Date" and a value of "2017-12-14".
        """
        self.attributes.append(NotificationAttribute(title, value))


class NotificationType:
    def __init__(self, event: Event = None):
        self.event = event

    def __repr__(self):
        return '<NotificationType: {}>'.format(self.action_type)

    @property
    def action_type(self) -> str:
        """
        The action_type string that this notification handles, for example
        ``"pretix.event.order.paid"``. Only one notification type should be registered
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
        notification.
        """
        raise NotImplementedError()  # NOQA

    def build_notification(self, logentry: LogEntry) -> Notification:
        """
        This is the main function that you should override. It is supposed to turn a log entry
        object into a notification object that can then be rendered e.g. into an email.
        """
        return Notification(
            logentry.event,
            logentry.display()
        )


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


class ActionRequiredNotificationType(NotificationType):
    required_permission = "can_change_orders"
    action_type = "pretix.event.action_required"
    verbose_name = _("Administrative action required")

    def build_notification(self, logentry: LogEntry):
        control_url = build_absolute_uri(
            'control:event.requiredactions',
            kwargs={
                'organizer': logentry.event.organizer.slug,
                'event': logentry.event.slug,
            }
        )

        n = Notification(
            event=logentry.event,
            title=_('Administrative action required'),
            detail=_('Something happened in your event that our system cannot handle automatically, e.g. an external '
                     'refund. You need to resolve it manually or choose to ignore it, depending on the issue at hand.'),
            url=control_url
        )
        n.add_action(_('View all unresolved problems'), control_url)
        return n


class ParametrizedOrderNotificationType(NotificationType):
    required_permission = "can_view_orders"

    def __init__(self, event, action_type, verbose_name, title):
        self._action_type = action_type
        self._verbose_name = verbose_name
        self._title = title
        super().__init__(event)

    @property
    def action_type(self):
        return self._action_type

    @property
    def verbose_name(self):
        return self._verbose_name

    def build_notification(self, logentry: LogEntry):
        order = logentry.content_object

        order_url = build_absolute_uri(
            'control:event.order',
            kwargs={
                'organizer': logentry.event.organizer.slug,
                'event': logentry.event.slug,
                'code': order.code
            }
        )

        n = Notification(
            event=logentry.event,
            title=self._title.format(order=order, event=logentry.event),
            url=order_url
        )
        n.add_attribute(_('Event'), order.event.name)
        n.add_attribute(_('Order code'), order.code)
        n.add_attribute(_('Order total'), money_filter(order.total, logentry.event.currency))
        n.add_attribute(_('Pending amount'), money_filter(order.pending_sum, logentry.event.currency))
        n.add_attribute(_('Order date'), date_format(order.datetime, 'SHORT_DATETIME_FORMAT'))
        n.add_attribute(_('Order status'), order.get_status_display())
        n.add_attribute(_('Order positions'), str(order.positions.count()))
        n.add_action(_('View order details'), order_url)
        return n


@receiver(register_notification_types, dispatch_uid="base_register_default_notification_types")
def register_default_notification_types(sender, **kwargs):
    return (
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.placed',
            _('New order placed'),
            _('A new order has been placed: {order.code}'),
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.placed.require_approval',
            _('New order requires approval'),
            _('A new order has been placed that requires approval: {order.code}'),
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.paid',
            _('Order marked as paid'),
            _('Order {order.code} has been marked as paid.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.canceled',
            _('Order canceled'),
            _('Order {order.code} has been canceled.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.expired',
            _('Order expired'),
            _('Order {order.code} has been marked as expired.'),
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.modified',
            _('Order information changed'),
            _('The ticket information of order {order.code} has been changed.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.contact.changed',
            _('Order contact address changed'),
            _('The contact address of order {order.code} has been changed.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.changed.*',
            _('Order changed'),
            _('Order {order.code} has been changed.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.overpaid',
            _('Order has been overpaid'),
            _('Order {order.code} has been overpaid.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.refund.created.externally',
            _('External refund of payment'),
            _('An external refund for {order.code} has occurred.')
        ),
        ParametrizedOrderNotificationType(
            sender,
            'pretix.event.order.refund.requested',
            _('Refund requested'),
            _('You have been requested to issue a refund for {order.code}.')
        ),
        ActionRequiredNotificationType(
            sender,
        )
    )
