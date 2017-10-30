import json
from decimal import Decimal

import dateutil.parser
import pytz
from django.dispatch import receiver
from django.utils import formats
from django.utils.formats import date_format
from django.utils.translation import pgettext_lazy, ugettext_lazy as _
from i18nfield.strings import LazyI18nString

from pretix.base.models import Event, ItemVariation, LogEntry, OrderPosition
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
    elif logentry.action_type == 'pretix.event.order.changed.subevent':
        old_se = str(event.subevents.get(pk=data['old_subevent']))
        new_se = str(event.subevents.get(pk=data['new_subevent']))
        return text + ' ' + _('Position #{posid}: Event date "{old_event}" ({old_price} {currency}) changed '
                              'to "{new_event}" ({new_price} {currency}).').format(
            posid=data.get('positionid', '?'),
            old_event=old_se, new_event=new_se,
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
    elif logentry.action_type == 'pretix.event.order.changed.add':
        item = str(event.items.get(pk=data['item']))
        if data['variation']:
            item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['variation']))
        if data['addon_to']:
            addon_to = OrderPosition.objects.get(order__event=event, pk=data['addon_to'])
            return text + ' ' + _('Position #{posid} created: {item} ({price} {currency}) as an add-on to '
                                  'position #{addon_to}.').format(
                posid=data.get('positionid', '?'),
                item=item, addon_to=addon_to.positionid,
                price=formats.localize(Decimal(data['price'])),
                currency=event.currency
            )
        else:
            return text + ' ' + _('Position #{posid} created: {item} ({price} {currency}).').format(
                posid=data.get('positionid', '?'),
                item=item,
                price=formats.localize(Decimal(data['price'])),
                currency=event.currency
            )
    elif logentry.action_type == 'pretix.event.order.changed.split':
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(pk=data['old_variation']))
        return text + ' ' + _('Position #{posid} ({old_item}, {old_price} {currency}) split into new order: {order}').format(
            old_item=old_item,
            posid=data.get('positionid', '?'),
            order=data['new_order'],
            old_price=formats.localize(Decimal(data['old_price'])),
            currency=event.currency
        )
    elif logentry.action_type == 'pretix.event.order.changed.split_from':
        return _('This order has been created by splitting the order {order}').format(
            order=data['original_order'],
        )


@receiver(signal=logentry_display, dispatch_uid="pretixcontrol_logentry_display")
def pretixcontrol_logentry_display(sender: Event, logentry: LogEntry, **kwargs):
    plains = {
        'pretix.event.comment': _('The event\'s internal comment has been updated.'),
        'pretix.event.order.modified': _('The order details have been changed.'),
        'pretix.event.order.unpaid': _('The order has been marked as unpaid.'),
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
        'pretix.event.order.email.sent': _('An unindentified type email has been sent.'),
        'pretix.event.order.email.custom_sent': _('A custom email has been sent.'),
        'pretix.event.order.email.expire_warning_sent': _('An email has been sent with a warning that the order is about '
                                                          'to expire.'),
        'pretix.event.order.email.order_canceled': _('An email has been sent to notify the user that the order has been canceled.'),
        'pretix.event.order.email.order_changed': _('An email has been sent to notify the user that the order has been changed.'),
        'pretix.event.order.email.order_free': _('An email has been sent to notify the user that the order has been received.'),
        'pretix.event.order.email.order_paid': _('An email has been sent to notify the user that payment has been received.'),
        'pretix.event.order.email.order_placed': _('An email has been sent to notify the user that the order has been received and requires payment.'),
        'pretix.event.order.email.resend': _('An email with a link to the order detail page has been resent to the user.'),
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
        'pretix.voucher.changed': _('The voucher has been changed.'),
        'pretix.voucher.deleted': _('The voucher has been deleted.'),
        'pretix.voucher.redeemed': _('The voucher has been redeemed in order {order_code}.'),
        'pretix.event.item.added': _('The product has been created.'),
        'pretix.event.item.changed': _('The product has been changed.'),
        'pretix.event.item.deleted': _('The product has been deleted.'),
        'pretix.event.item.variation.added': _('The variation "{value}" has been created.'),
        'pretix.event.item.variation.deleted': _('The variation "{value}" has been deleted.'),
        'pretix.event.item.variation.changed': _('The variation "{value}" has been changed.'),
        'pretix.event.item.addons.added': _('An add-on has been added to this product.'),
        'pretix.event.item.addons.removed': _('An add-on has been removed from this product.'),
        'pretix.event.item.addons.changed': _('An add-on has been changed on this product.'),
        'pretix.event.quota.added': _('The quota has been added.'),
        'pretix.event.quota.deleted': _('The quota has been deleted.'),
        'pretix.event.quota.changed': _('The quota has been changed.'),
        'pretix.event.category.added': _('The category has been added.'),
        'pretix.event.category.deleted': _('The category has been deleted.'),
        'pretix.event.category.changed': _('The category has been changed.'),
        'pretix.event.question.added': _('The question has been added.'),
        'pretix.event.question.deleted': _('The question has been deleted.'),
        'pretix.event.question.changed': _('The question has been changed.'),
        'pretix.event.taxrule.added': _('The tax rule has been added.'),
        'pretix.event.taxrule.deleted': _('The tax rule has been deleted.'),
        'pretix.event.taxrule.changed': _('The tax rule has been changed.'),
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
        'pretix.waitinglist.voucher': _('A voucher has been sent to a person on the waiting list.'),
        'pretix.team.created': _('The team has been created.'),
        'pretix.team.changed': _('The team settings have been changed.'),
        'pretix.team.deleted': _('The team has been deleted.'),
        'pretix.subevent.deleted': pgettext_lazy('subevent', 'The event date has been deleted.'),
        'pretix.subevent.changed': pgettext_lazy('subevent', 'The event date has been changed.'),
        'pretix.subevent.added': pgettext_lazy('subevent', 'The event date has been created.'),
        'pretix.subevent.quota.added': pgettext_lazy('subevent', 'A quota has been added to the event date.'),
        'pretix.subevent.quota.changed': pgettext_lazy('subevent', 'A quota has been changed on the event date.'),
        'pretix.subevent.quota.deleted': pgettext_lazy('subevent', 'A quota has been removed from the event date.'),
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

    if logentry.action_type == 'pretix.control.views.checkin':
        dt = dateutil.parser.parse(data.get('datetime'))
        tz = pytz.timezone(sender.settings.timezone)
        dt_formatted = date_format(dt.astimezone(tz), "SHORT_DATETIME_FORMAT")

        if data.get('first'):
            return _('Position #{posid} has been checked in manually at {datetime}.').format(
                posid=data.get('positionid'),
                datetime=dt_formatted
            )
        return _('Position #{posid} has been checked in again at {datetime}.').format(
            posid=data.get('positionid'),
            datetime=dt_formatted
        )

    if logentry.action_type == 'pretix.team.member.added':
        return _('{user} has been added to the team.').format(user=data.get('email'))

    if logentry.action_type == 'pretix.team.member.removed':
        return _('{user} has been removed from the team.').format(user=data.get('email'))

    if logentry.action_type == 'pretix.team.member.joined':
        return _('{user} has joined the team using the invite sent to {email}.').format(
            user=data.get('email'), email=data.get('invite_email')
        )

    if logentry.action_type == 'pretix.team.invite.created':
        return _('{user} has been invited to the team.').format(user=data.get('email'))

    if logentry.action_type == 'pretix.team.invite.deleted':
        return _('The invite for {user} has been revoked.').format(user=data.get('email'))

    if logentry.action_type == 'pretix.team.token.created':
        return _('The token "{name}" has been created.').format(name=data.get('name'))

    if logentry.action_type == 'pretix.team.token.deleted':
        return _('The token "{name}" has been revoked.').format(name=data.get('name'))

    if logentry.action_type == 'pretix.user.settings.changed':
        text = str(_('Your account settings have been changed.'))
        if 'email' in data:
            text = text + ' ' + str(_('Your email address has been changed to {email}.').format(email=data['email']))
        if 'new_pw' in data:
            text = text + ' ' + str(_('Your password has been changed.'))
        return text
