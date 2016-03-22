from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import logentry_display


@receiver(signal=logentry_display, dispatch_uid="pretixcontrol_logentry_display")
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    plains = {
        'pretix.event.order.modified': _('The order details have been modified.'),
        'pretix.event.order.unpaid': _('The order has been marked as unpaid.'),
        'pretix.event.order.resend': _('The link to the order detail page has been resent to the user.'),
        'pretix.event.order.expirychanged': _('The order\'s expiry date has been changed.'),
        'pretix.event.order.paid': _('The order has been marked as paid.'),
        'pretix.event.order.refunded': _('The order has been refunded.'),
        'pretix.event.order.cancelled': _('The order has been cancelled.'),
        'pretix.event.order.placed': _('The order has been created.'),
    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]
