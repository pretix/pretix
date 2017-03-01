import json
from decimal import Decimal

from django.dispatch import receiver
from django.utils import formats
from django.utils.translation import ugettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretix.base.models import Event, ItemVariation, LogEntry
from pretix.base.signals import logentry_display

OVERVIEW_BLACKLIST = [
    'pretix.plugins.sendmail.order.email.sent'
]


def _display_order_changed(event: Event, logentry: LogEntry):
    data = json.loads(logentry.data)

    text = _('The order has been changed:')
    if logentry.action_type == 'pretix.event.order.changed.item':
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['old_variation']))
        new_item = str(event.items.get(pk=data['new_item']))
        if data['new_variation']:
            new_item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['new_variation']))
        return text + ' ' + _('Position #{posid}: {old_item} ({old_price} {currency}) changed '
                              'to {new_item} ({new_price} {currency}).').format(
            posid=data.get('positionid', '?'),
            old_item=old_item, new_item=new_item,
            old_price=formats.localize(Decimal(data['old_price'])),
            new_price=formats.localize(Decimal(data['new_price'])),
            currency=event.currency
        )
    elif logentry.action_type == 'pretix.event.order.changed.price':
        return text + ' ' + _('Price of position #{posid} changed from {old_price} {currency} '
                              'to {new_price} {currency}.').format(
            posid=data.get('positionid', '?'),
            old_price=formats.localize(Decimal(data['old_price'])),
            new_price=formats.localize(Decimal(data['new_price'])),
            currency=event.currency
        )
    elif logentry.action_type == 'pretix.event.order.changed.cancel':
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(pk=data['old_variation']))
        return text + ' ' + _('Position #{posid} ({old_item}, {old_price} {currency}) removed.').format(
            posid=data.get('positionid', '?'),
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
        'pretix.event.order.contact.changed': _('The email address has been changed from "{old_email}" '
                                                'to "{new_email}".'),
        'pretix.event.order.invoice.generated': _('The invoice has been generated.'),
        'pretix.event.order.invoice.regenerated': _('The invoice has been regenerated.'),
        'pretix.event.order.invoice.reissued': _('The invoice has been reissued.'),
        'pretix.event.order.comment': _('The order\'s internal comment has been updated.'),
        'pretix.event.order.payment.changed': _('The payment method has been changed.'),
        'pretix.event.order.expire_warning_sent': _('An email has been sent with a warning that the order is about '
                                                    'to expire.'),
        'pretix.user.settings.2fa.enabled': _('Two-factor authentication has been enabled.'),
        'pretix.user.settings.2fa.disabled': _('Two-factor authentication has been disabled.'),
        'pretix.user.settings.2fa.regenemergency': _('Your two-factor emergency codes have been regenerated.'),
        'pretix.user.settings.2fa.device.added': _('A new two-factor authentication device "{name}" has been added to '
                                                   'your account.'),
        'pretix.user.settings.2fa.device.deleted': _('The two-factor authentication device "{name}" has been removed '
                                                     'from your account.'),
        'pretix.control.auth.user.forgot_password.mail_sent': _('Password reset mail sent.'),
        'pretix.control.auth.user.forgot_password.recovered': _('The password has been reset.'),
        'pretix.voucher.added': _('The voucher has been created.'),
        'pretix.voucher.added.waitinglist': _('The voucher has been created and sent to a person on the waiting list.'),
        'pretix.voucher.changed': _('The voucher has been modified.'),
        'pretix.voucher.deleted': _('The voucher has been deleted.'),
        'pretix.voucher.redeemed': _('The voucher has been redeemed in order {order_code}.'),
        'pretix.event.item.added': _('The product has been created.'),
        'pretix.event.item.changed': _('The product has been modified.'),
        'pretix.event.item.deleted': _('The product has been deleted.'),
        'pretix.event.item.variation.added': _('The variation "{value}" has been created.'),
        'pretix.event.item.variation.deleted': _('The variation "{value}" has been deleted.'),
        'pretix.event.item.variation.changed': _('The variation "{value}" has been modified.'),
        'pretix.event.item.addons.added': _('An add-on has been added to this product.'),
        'pretix.event.item.addons.removed': _('An add-on has been removed from this product.'),
        'pretix.event.item.addons.changed': _('An add-on has been changed on this product.'),
        'pretix.event.quota.added': _('The quota has been added.'),
        'pretix.event.quota.deleted': _('The quota has been deleted.'),
        'pretix.event.quota.changed': _('The quota has been modified.'),
        'pretix.event.category.added': _('The category has been added.'),
        'pretix.event.category.deleted': _('The category has been deleted.'),
        'pretix.event.category.changed': _('The category has been modified.'),
        'pretix.event.question.added': _('The question has been added.'),
        'pretix.event.question.deleted': _('The question has been deleted.'),
        'pretix.event.question.changed': _('The question has been modified.'),
        'pretix.event.settings': _('The event settings have been changed.'),
        'pretix.event.tickets.settings': _('The ticket download settings have been changed.'),
        'pretix.event.plugins.enabled': _('A plugin has been enabled.'),
        'pretix.event.plugins.disabled': _('A plugin has been disabled.'),
        'pretix.event.live.activated': _('The shop has been taken live.'),
        'pretix.event.live.deactivated': _('The shop has been taken offline.'),
        'pretix.event.changed': _('The event settings have been changed.'),
        'pretix.event.question.option.added': _('An answer option has been added to the question.'),
        'pretix.event.question.option.deleted': _('An answer option has been removed from the question.'),
        'pretix.event.question.option.changed': _('An answer option has been changed.'),
        'pretix.event.permissions.added': _('A user has been added to the event team.'),
        'pretix.event.permissions.invited': _('A user has been invited to the event team.'),
        'pretix.event.permissions.changed': _('A user\'s permissions have been changed.'),
        'pretix.event.permissions.deleted': _('A user has been removed from the event team.'),
        'pretix.waitinglist.voucher': _('A voucher has been sent to a person on the waiting list.')
    }

    data = json.loads(logentry.data)

    if logentry.action_type.startswith('pretix.event.item.variation'):
        if 'value' not in data:
            # Backwards compatibility
            var = ItemVariation.objects.filter(id=data['id']).first()
            if var:
                data['value'] = str(var.value)
            else:
                data['value'] = '?'
        else:
            data['value'] = LazyI18nString(data['value'])

    if logentry.action_type in plains:
        return plains[logentry.action_type].format_map(data)

    if logentry.action_type.startswith('pretix.event.order.changed'):
        return _display_order_changed(sender, logentry)

    if logentry.action_type.startswith('pretix.event.payment.provider.'):
        return _('The settings of a payment provider have been changed.')

    if logentry.action_type.startswith('pretix.event.tickets.provider.'):
        return _('The settings of a ticket output provider have been changed.')

    if logentry.action_type == 'pretix.user.settings.changed':
        text = str(_('Your account settings have been changed.'))
        if 'email' in data:
            text = text + ' ' + str(_('Your email address has been changed to {email}.').format(email=data['email']))
        if 'new_pw' in data:
            text = text + ' ' + str(_('Your password has been changed.'))
        return text
