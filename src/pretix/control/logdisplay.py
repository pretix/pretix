import json
from decimal import Decimal

from django.dispatch import receiver
from django.utils import formats
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Event, ItemVariation, LogEntry
from pretix.base.signals import logentry_display


def _display_order_changed(event: Event, logentry: LogEntry):
    data = json.loads(logentry.data)

    text = _('The order has been changed:')
    if logentry.action_type == 'pretix.event.order.changed.item':
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(event.itemvariations.get(pk=data['old_variation']))
        new_item = str(event.items.get(pk=data['new_item']))
        if data['new_variation']:
            new_item += ' - ' + str(event.itemvariations.get(pk=data['new_variation']))
        return text + ' ' + _('{old_item} ({old_price} {currency}) changed to {new_item} ({new_price} {currency}).').format(
            old_item=old_item, new_item=new_item,
            old_price=formats.localize(Decimal(data['old_price'])),
            new_price=formats.localize(Decimal(data['new_price'])),
            currency=event.currency
        )
    elif logentry.action_type == 'pretix.event.order.changed.price':
        return text + ' ' + _('Price of a position changed from {old_price} {currency} to {new_price} {currency}.').format(
            old_price=formats.localize(Decimal(data['old_price'])),
            new_price=formats.localize(Decimal(data['new_price'])),
            currency=event.currency
        )
    elif logentry.action_type == 'pretix.event.order.changed.cancel':
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(pk=data['old_variation']))
        return text + ' ' + _('{old_item} ({old_price} {currency}) removed.').format(
            old_item=old_item,
            old_price=formats.localize(Decimal(data['old_price'])),
            currency=event.currency
        )


@receiver(signal=logentry_display, dispatch_uid="pretixcontrol_logentry_display")
def pretixcontrol_logentry_display(sender: Event, logentry: LogEntry, **kwargs):
    plains = {
        'pretix.event.order.modified': _('The order details have been modified.'),
        'pretix.event.order.unpaid': _('The order has been marked as unpaid.'),
        'pretix.event.order.resend': _('The link to the order detail page has been resent to the user.'),
        'pretix.event.order.secret.changed': _('The order\'s secret has been changed.'),
        'pretix.event.order.expirychanged': _('The order\'s expiry date has been changed.'),
        'pretix.event.order.expired': _('The order has been marked as expired.'),
        'pretix.event.order.paid': _('The order has been marked as paid.'),
        'pretix.event.order.refunded': _('The order has been refunded.'),
        'pretix.event.order.canceled': _('The order has been canceled.'),
        'pretix.event.order.placed': _('The order has been created.'),
        'pretix.event.order.invoice.generated': _('The invoice has been generated.'),
        'pretix.event.order.invoice.regenerated': _('The invoice has been regenerated.'),
        'pretix.event.order.invoice.reissued': _('The invoice has been reissued.'),
        'pretix.event.order.comment': _('The order\'s internal comment has been updated.'),
        'pretix.event.order.payment.changed': _('The payment method has been changed.'),
        'pretix.event.order.expire_warning_sent': _('An email has been sent with a warning that the order is about to expire.'),
        'pretix.user.settings.2fa.enabled': _('Two-factor authentication has been enabled.'),
        'pretix.user.settings.2fa.disabled': _('Two-factor authentication has been disabled.'),
        'pretix.user.settings.2fa.regenemergency': _('Your two-factor emergency codes have been regenerated.'),
        'pretix.control.auth.user.forgot_password.mail_sent': _('Password reset mail sent.'),
        'pretix.control.auth.user.forgot_password.recovered': _('The password has been reset.')

    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]

    if logentry.action_type.startswith('pretix.event.order.changed'):
        return _display_order_changed(sender, logentry)

    if logentry.action_type.startswith('pretix.event.order.contact.changed'):
        data = json.loads(logentry.data)
        return _('The email address has been changed from "{old}" to "{new}".').format(
            old=data['old_email'],
            new=data['new_email'],
        )

    if logentry.action_type == 'pretix.user.settings.2fa.device.added':
        data = json.loads(logentry.data)
        return _('A new two-factor authentication device "{name}" has been added to your account.').format(
            name=data['name']
        )
    if logentry.action_type == 'pretix.user.settings.2fa.device.deleted':
        data = json.loads(logentry.data)
        return _('The two-factor authentication device "{name}" has been removed from your account.').format(
            name=data['name']
        )
    if logentry.action_type == 'pretix.user.settings.changed':
        data = json.loads(logentry.data)
        text = str(_('Your account settings have been changed.'))
        if 'email' in data:
            text = text + ' ' + str(_('Your email address has been changed to {email}.').format(email=data['email']))
        if 'new_pw' in data:
            text = text + ' ' + str(_('Your password has been changed.'))
        return text
