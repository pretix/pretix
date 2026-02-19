#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel, Flavia Bastos, Jakob Schnell, Sean Perkins,
# Sohalt, Tobias Kunze, Ture Gjørup, domke
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from collections import defaultdict
from decimal import Decimal
from typing import Optional

import bleach
import dateutil.parser
from django.dispatch import receiver
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from i18nfield.strings import LazyI18nString

from pretix.base.datasync.datasync import datasync_providers
from pretix.base.logentrytypes import (
    DiscountLogEntryType, EventLogEntryType, ItemCategoryLogEntryType,
    ItemLogEntryType, LogEntryType, OrderLogEntryType, QuestionLogEntryType,
    QuotaLogEntryType, TaxRuleLogEntryType, VoucherLogEntryType,
    WaitingListEntryLogEntryType, log_entry_types,
)
from pretix.base.models import (
    Checkin, CheckinList, Event, ItemVariation, LogEntry, OrderPosition,
    TaxRule,
)
from pretix.base.models.orders import PrintLog
from pretix.base.signals import (
    app_cache, logentry_display, orderposition_blocked_display,
)
from pretix.base.templatetags.money import money_filter

OVERVIEW_BANLIST = [
    'pretix.plugins.sendmail.order.email.sent'
]


class OrderChangeLogEntryType(OrderLogEntryType):
    prefix = _('The order has been changed:')

    def display(self, logentry, data):
        return format_html('{} {}', self.prefix, self.display_prefixed(logentry.event, logentry, data))

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return super().display(logentry, data)


class OrderPositionChangeLogEntryType(OrderChangeLogEntryType):
    prefix = _('The order has been changed:')

    def display(self, logentry, data):
        return super().display(logentry, {**data, 'posid': data.get('positionid', '?')})


@log_entry_types.new()
class OrderItemChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.item'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['old_variation']))
        new_item = str(event.items.get(pk=data['new_item']))
        if data['new_variation']:
            new_item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['new_variation']))
        return _('Position #{posid}: {old_item} ({old_price}) changed to {new_item} ({new_price}).').format(
            posid=data.get('positionid', '?'),
            old_item=old_item, new_item=new_item,
            old_price=money_filter(Decimal(data['old_price']), event.currency),
            new_price=money_filter(Decimal(data['new_price']), event.currency),
        )


@log_entry_types.new()
class OrderMembershipChanged(OrderPositionChangeLogEntryType):
    action_type = 'pretix.event.order.changed.membership'
    plain = _('Position #{posid}: Used membership changed.')


@log_entry_types.new()
class OrderSeatChanged(OrderPositionChangeLogEntryType):
    action_type = 'pretix.event.order.changed.seat'
    plain = _('Position #{posid}: Seat "{old_seat}" changed to "{new_seat}".')


@log_entry_types.new()
class OrderSubeventChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.subevent'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        old_se = str(event.subevents.get(pk=data['old_subevent']))
        new_se = str(event.subevents.get(pk=data['new_subevent']))
        return _('Position #{posid}: Event date "{old_event}" ({old_price}) changed '
                 'to "{new_event}" ({new_price}).').format(
            posid=data.get('positionid', '?'),
            old_event=old_se, new_event=new_se,
            old_price=money_filter(Decimal(data['old_price']), event.currency),
            new_price=money_filter(Decimal(data['new_price']), event.currency),
        )


@log_entry_types.new()
class OrderPriceChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.price'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return _('Price of position #{posid} changed from {old_price} to {new_price}.').format(
            posid=data.get('positionid', '?'),
            old_price=money_filter(Decimal(data['old_price']), event.currency),
            new_price=money_filter(Decimal(data['new_price']), event.currency),
        )


@log_entry_types.new()
class OrderTaxRuleChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.tax_rule'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        if 'positionid' in data:
            return _('Tax rule of position #{posid} changed from {old_rule} to {new_rule}.').format(
                posid=data.get('positionid', '?'),
                old_rule=TaxRule.objects.get(pk=data['old_taxrule']) if data['old_taxrule'] else '–',
                new_rule=TaxRule.objects.get(pk=data['new_taxrule']),
            )
        elif 'fee' in data:
            return _('Tax rule of fee #{fee} changed from {old_rule} to {new_rule}.').format(
                fee=data.get('fee', '?'),
                old_rule=TaxRule.objects.get(pk=data['old_taxrule']) if data['old_taxrule'] else '–',
                new_rule=TaxRule.objects.get(pk=data['new_taxrule']),
            )


@log_entry_types.new()
class OrderFeeAdded(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.addfee'
    plain = _('A fee has been added')


@log_entry_types.new()
class OrderRecomputed(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.recomputed'
    plain = _('Taxes and rounding have been recomputed')


@log_entry_types.new()
class OrderFeeChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.feevalue'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return _('A fee was changed from {old_price} to {new_price}.').format(
            old_price=money_filter(Decimal(data['old_price']), event.currency),
            new_price=money_filter(Decimal(data['new_price']), event.currency),
        )


@log_entry_types.new()
class OrderFeeRemoved(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.cancelfee'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return _('A fee of {old_price} was removed.').format(
            old_price=money_filter(Decimal(data['old_price']), event.currency),
        )


@log_entry_types.new()
class OrderCanceled(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.cancel'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(pk=data['old_variation']))
        return _('Position #{posid} ({old_item}, {old_price}) canceled.').format(
            posid=data.get('positionid', '?'),
            old_item=old_item,
            old_price=money_filter(Decimal(data['old_price']), event.currency),
        )


@log_entry_types.new()
class OrderPositionAdded(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.add'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        item = str(event.items.get(pk=data['item']))
        if data['variation']:
            item += ' - ' + str(ItemVariation.objects.get(item__event=event, pk=data['variation']))
        if data['addon_to']:
            addon_to = OrderPosition.objects.get(order__event=event, pk=data['addon_to'])
            return _('Position #{posid} created: {item} ({price}) as an add-on to position #{addon_to}.').format(
                posid=data.get('positionid', '?'),
                item=item, addon_to=addon_to.positionid,
                price=money_filter(Decimal(data['price']), event.currency),
            )
        else:
            return _('Position #{posid} created: {item} ({price}).').format(
                posid=data.get('positionid', '?'),
                item=item,
                price=money_filter(Decimal(data['price']), event.currency),
            )


@log_entry_types.new()
class OrderSecretChanged(OrderPositionChangeLogEntryType):
    action_type = 'pretix.event.order.changed.secret'
    plain = _('A new secret has been generated for position #{posid}.')


@log_entry_types.new()
class OrderValidFromChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.valid_from'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return _('The validity start date for position #{posid} has been changed to {value}.').format(
            posid=data.get('positionid', '?'),
            value=date_format(dateutil.parser.parse(data.get('new_value')), 'SHORT_DATETIME_FORMAT') if data.get(
                'new_value') else '–'
        )


@log_entry_types.new()
class OrderValidUntilChanged(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.valid_until'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        return _('The validity end date for position #{posid} has been changed to {value}.').format(
            posid=data.get('positionid', '?'),
            value=date_format(dateutil.parser.parse(data.get('new_value')), 'SHORT_DATETIME_FORMAT') if data.get('new_value') else '–'
        )


@log_entry_types.new()
class OrderChangedBlockAdded(OrderPositionChangeLogEntryType):
    action_type = 'pretix.event.order.changed.add_block'
    plain = _('A block has been added for position #{posid}.')


@log_entry_types.new()
class OrderChangedBlockRemoved(OrderPositionChangeLogEntryType):
    action_type = 'pretix.event.order.changed.remove_block'
    plain = _('A block has been removed for position #{posid}.')


@log_entry_types.new()
class OrderChangedSplit(OrderChangeLogEntryType):
    action_type = 'pretix.event.order.changed.split'

    def display_prefixed(self, event: Event, logentry: LogEntry, data):
        old_item = str(event.items.get(pk=data['old_item']))
        if data['old_variation']:
            old_item += ' - ' + str(ItemVariation.objects.get(pk=data['old_variation']))
        url = reverse('control:event.order', kwargs={
            'event': event.slug,
            'organizer': event.organizer.slug,
            'code': data['new_order']
        })
        return format_html(
            _('Position #{posid} ({old_item}, {old_price}) split into new order: {order}'),
            old_item=escape(old_item),
            posid=data.get('positionid', '?'),
            order=format_html('<a href="{}">{}</a>', url, data['new_order']),
            old_price=money_filter(Decimal(data['old_price']), event.currency),
        )


@log_entry_types.new()
class OrderChangedSplitFrom(OrderLogEntryType):
    action_type = 'pretix.event.order.changed.split_from'

    def display(self, logentry: LogEntry, data):
        url = reverse('control:event.order', kwargs={
            'event': logentry.event.slug,
            'organizer': logentry.event.organizer.slug,
            'code': data['original_order']
        })
        return format_html(
            _('This order has been created by splitting the order {order}'),
            order=format_html('<a href="{}">{}</a>', url, data['original_order']),
        )


@log_entry_types.new_from_dict({
    'pretix.event.checkin.unknown': (
        _('Unknown scan of code "{barcode}…" at {datetime} for list "{list}", type "{type}".'),
        _('Unknown scan of code "{barcode}…" for list "{list}", type "{type}".'),
    ),
    'pretix.event.checkin.revoked': (
        _('Scan of revoked code "{barcode}…" at {datetime} for list "{list}", type "{type}", was uploaded.'),
        _('Scan of revoked code "{barcode}" for list "{list}", type "{type}", was uploaded.'),
    ),
    'pretix.event.checkin.denied': (
        _('Denied scan of position #{posid} at {datetime} for list "{list}", type "{type}", error code "{errorcode}".'),
        _('Denied scan of position #{posid} for list "{list}", type "{type}", error code "{errorcode}".'),
    ),
    'pretix.event.checkin.annulled': (
        _('Annulled scan of position #{posid} at {datetime} for list "{list}", type "{type}".'),
        _('Annulled scan of position #{posid} for list "{list}", type "{type}".'),
    ),
    'pretix.event.checkin.annulment.ignored': (
        _('Ignored annulment of position #{posid} at {datetime} for list "{list}", type "{type}".'),
        _('Ignored annulment of position #{posid} for list "{list}", type "{type}".'),
    ),
    'pretix.control.views.checkin.reverted': _('The check-in of position #{posid} on list "{list}" has been reverted.'),
    'pretix.event.checkin.reverted': _('The check-in of position #{posid} on list "{list}" has been reverted.'),
})
class CheckinErrorLogEntryType(OrderLogEntryType):
    def display(self, logentry: LogEntry, data):
        return self.display_plain(self.plain, logentry, data)

    def display_plain(self, plain, logentry: LogEntry, data):
        if isinstance(plain, tuple):
            plain_with_dt, plain_without_dt = plain
        else:
            plain_with_dt, plain_without_dt = plain, plain

        data = defaultdict(lambda: '?', data)

        event = logentry.event

        if 'list' in data and event:
            try:
                data['list'] = event.checkin_lists.get(pk=data.get('list')).name
            except CheckinList.DoesNotExist:
                data['list'] = _("(unknown)")
        else:
            data['list'] = _("(unknown)")

        data['barcode'] = data.get('barcode', '')[:16]
        data['posid'] = logentry.parsed_data.get('positionid', '?')

        if 'datetime' in data:
            dt = dateutil.parser.parse(data.get('datetime'))
            if abs((logentry.datetime - dt).total_seconds()) > 5 or data.get('forced'):
                if event:
                    data['datetime'] = date_format(dt.astimezone(event.timezone), "SHORT_DATETIME_FORMAT")
                return str(plain_with_dt).format_map(data)

        return str(plain_without_dt).format_map(data)


@log_entry_types.new('pretix.event.checkin')
class CheckinLogEntryType(CheckinErrorLogEntryType):
    def display(self, logentry: LogEntry, data):
        if data.get('type') == Checkin.TYPE_EXIT:
            return self.display_plain((
                _('Position #{posid} has been checked out at {datetime} for list "{list}".'),
                _('Position #{posid} has been checked out for list "{list}".'),
            ), logentry, data)
        elif data.get('first'):
            return self.display_plain((
                _('Position #{posid} has been checked in at {datetime} for list "{list}".'),
                _('Position #{posid} has been checked in for list "{list}".'),
            ), logentry, data)
        elif data.get('forced'):
            return self.display_plain(
                _('A scan for position #{posid} at {datetime} for list "{list}" has been uploaded even though it has '
                  'been scanned already.'),
                logentry, data
            )
        else:
            return self.display_plain(
                _('Position #{posid} has been scanned and rejected because it has already been scanned before '
                  'on list "{list}".'),
                logentry, data
            )


@log_entry_types.new()
class OrderConsentLogEntryType(OrderLogEntryType):
    action_type = 'pretix.event.order.consent'

    def display(self, logentry: LogEntry, data):
        return _('The user confirmed the following message: "{}"').format(
            bleach.clean(data.get('msg'), tags=set(), strip=True)
        )


@log_entry_types.new()
class OrderCanceledLogEntryType(OrderLogEntryType):
    action_type = 'pretix.event.order.canceled'

    def display(self, logentry: LogEntry, data):
        comment = data.get('comment')
        if comment:
            return _('The order has been canceled (comment: "{comment}").').format(comment=comment)
        else:
            return _('The order has been canceled.')


@log_entry_types.new()
class OrderPrintLogEntryType(OrderLogEntryType):
    action_type = 'pretix.event.order.print'

    def display(self, logentry: LogEntry, data):
        return _('Position #{posid} has been printed at {datetime} with type "{type}".').format(
            posid=data.get('positionid'),
            datetime=date_format(
                dateutil.parser.parse(data["datetime"]).astimezone(logentry.event.timezone),
                "SHORT_DATETIME_FORMAT"
            ) if logentry.event else data["datetime"],
            type=dict(PrintLog.PRINT_TYPES)[data["type"]],
        )


class OrderDataSyncLogEntryType(OrderLogEntryType):
    def display(self, logentry, data):
        try:
            from pretix.base.datasync.datasync import datasync_providers
            provider_class, meta = datasync_providers.get(identifier=data['provider'])
            data['provider_display_name'] = provider_class.display_name
        except (KeyError, AttributeError):
            data['provider_display_name'] = data.get('provider')
        return super().display(logentry, data)


@log_entry_types.new_from_dict({
    "pretix.event.order.data_sync.success": _("Data successfully transferred to {provider_display_name}."),
})
class OrderDataSyncSuccessLogEntryType(OrderDataSyncLogEntryType):
    def display(self, logentry, data):
        links = []
        if data.get('provider') and data.get('objects'):
            prov, meta = datasync_providers.get(identifier=data['provider'])
            if prov:
                for objs in data['objects'].values():
                    links.append(", ".join(
                        prov.get_external_link_html(logentry.event, obj['external_link_href'], obj['external_link_display_name'])
                        for obj in objs
                        if obj and obj.get('external_link_href') and obj.get('external_link_display_name')
                    ))

        return mark_safe(escape(super().display(logentry, data)) + "".join("<p>" + link + "</p>" for link in links))


@log_entry_types.new_from_dict({
    "pretix.event.order.data_sync.failed.config": _("Transferring data to {provider_display_name} failed due to invalid configuration:"),
    "pretix.event.order.data_sync.failed.exceeded": _("Maximum number of retries exceeded while transferring data to {provider_display_name}:"),
    "pretix.event.order.data_sync.failed.permanent": _("Error while transferring data to {provider_display_name}:"),
    "pretix.event.order.data_sync.failed.internal": _("Internal error while transferring data to {provider_display_name}."),
    "pretix.event.order.data_sync.failed.timeout": _("Internal error while transferring data to {provider_display_name}."),
})
class OrderDataSyncErrorLogEntryType(OrderDataSyncLogEntryType):
    def display(self, logentry, data):
        errmes = data["error"]
        if not isinstance(errmes, list):
            errmes = [errmes]
        return mark_safe(escape(super().display(logentry, data)) + "".join("<p>" + escape(msg) + "</p>" for msg in errmes))


@receiver(signal=logentry_display, dispatch_uid="pretixcontrol_logentry_display")
def pretixcontrol_logentry_display(sender: Event, logentry: LogEntry, **kwargs):

    if logentry.action_type.startswith('pretix.event.payment.provider.'):
        return _('The settings of a payment provider have been changed.')

    if logentry.action_type.startswith('pretix.event.tickets.provider.'):
        return _('The settings of a ticket output provider have been changed.')


@receiver(signal=orderposition_blocked_display, dispatch_uid="pretixcontrol_orderposition_blocked_display")
def pretixcontrol_orderposition_blocked_display(sender: Event, orderposition, block_name, **kwargs):
    if block_name == 'admin':
        return _('Blocked manually')
    elif block_name.startswith('api:'):
        return _('Blocked because of an API integration')


@log_entry_types.new_from_dict({
    'pretix.event.order.deleted': _('The test mode order {code} has been deleted.'),
    'pretix.event.order.modified': _('The order details have been changed.'),
    'pretix.event.order.unpaid': _('The order has been marked as unpaid.'),
    'pretix.event.order.secret.changed': _('The order\'s secret has been changed.'),
    'pretix.event.order.expirychanged': _('The order\'s expiry date has been changed.'),
    'pretix.event.order.valid_if_pending.set': _('The order has been set to be usable before it is paid.'),
    'pretix.event.order.valid_if_pending.unset': _('The order has been set to require payment before use.'),
    'pretix.event.order.expired': _('The order has been marked as expired.'),
    'pretix.event.order.paid': _('The order has been marked as paid.'),
    'pretix.event.order.cancellationrequest.deleted': _('The cancellation request has been deleted.'),
    'pretix.event.order.refunded': _('The order has been refunded.'),
    'pretix.event.order.reactivated': _('The order has been reactivated.'),
    'pretix.event.order.placed': _('The order has been created.'),
    'pretix.event.order.placed.require_approval': _(
        'The order requires approval before it can continue to be processed.'),
    'pretix.event.order.approved': _('The order has been approved.'),
    'pretix.event.order.denied': _('The order has been denied (comment: "{comment}").'),
    'pretix.event.order.contact.changed': _('The email address has been changed from "{old_email}" '
                                            'to "{new_email}".'),
    'pretix.event.order.contact.confirmed': _(
        'The email address has been confirmed to be working (the user clicked on a link '
        'in the email for the first time).'),
    'pretix.event.order.phone.changed': _('The phone number has been changed from "{old_phone}" '
                                          'to "{new_phone}".'),
    'pretix.event.order.customer.changed': _('The customer account has been changed.'),
    'pretix.event.order.locale.changed': _('The order locale has been changed.'),
    'pretix.event.order.invoice.generated': _('The invoice has been generated.'),
    'pretix.event.order.invoice.failed': _('The invoice could not be generated.'),
    'pretix.event.order.invoice.regenerated': _('The invoice has been regenerated.'),
    'pretix.event.order.invoice.reissued': _('The invoice has been reissued.'),
    'pretix.event.order.invoice.sent': _('The invoice {full_invoice_no} has been sent.'),
    'pretix.event.order.invoice.sending_failed': _('The transmission of invoice {full_invoice_no} has failed.'),
    'pretix.event.order.invoice.testmode_ignored': _('Invoice {full_invoice_no} has not been transmitted because '
                                                     'the transmission provider does not support test mode invoices.'),
    'pretix.event.order.invoice.retransmitted': _('The invoice {full_invoice_no} has been scheduled for retransmission.'),
    'pretix.event.order.comment': _('The order\'s internal comment has been updated.'),
    'pretix.event.order.custom_followup_at': _('The order\'s follow-up date has been updated.'),
    'pretix.event.order.checkin_attention': _('The order\'s flag to require attention at check-in has been '
                                              'toggled.'),
    'pretix.event.order.checkin_text': _('The order\'s check-in text has been changed.'),
    'pretix.event.order.pretix.event.order.valid_if_pending': _('The order\'s flag to be considered valid even if '
                                                                'unpaid has been toggled.'),
    'pretix.event.order.payment.changed': _('A new payment {local_id} has been started instead of the previous one.'),
    'pretix.event.order.email.sent': _('An unidentified type email has been sent.'),
    'pretix.event.order.email.error': _('Sending of an email has failed.'),
    'pretix.event.order.email.attachments.skipped': _('The email has been sent without attached tickets since they '
                                                      'would have been too large to be likely to arrive.'),
    'pretix.event.order.email.invoice': _('An invoice email has been sent.'),
    'pretix.event.order.email.custom_sent': _('A custom email has been sent.'),
    'pretix.event.order.position.email.custom_sent': _('A custom email has been sent to an attendee.'),
    'pretix.event.order.email.download_reminder_sent': _('An email has been sent with a reminder that the ticket '
                                                         'is available for download.'),
    'pretix.event.order.email.expire_warning_sent': _('An email has been sent with a warning that the order is about '
                                                      'to expire.'),
    'pretix.event.order.email.order_canceled': _(
        'An email has been sent to notify the user that the order has been canceled.'),
    'pretix.event.order.email.event_canceled': _('An email has been sent to notify the user that the event has '
                                                 'been canceled.'),
    'pretix.event.order.email.order_changed': _(
        'An email has been sent to notify the user that the order has been changed.'),
    'pretix.event.order.email.order_free': _(
        'An email has been sent to notify the user that the order has been received.'),
    'pretix.event.order.email.order_paid': _(
        'An email has been sent to notify the user that payment has been received.'),
    'pretix.event.order.email.order_denied': _(
        'An email has been sent to notify the user that the order has been denied.'),
    'pretix.event.order.email.order_approved': _('An email has been sent to notify the user that the order has '
                                                 'been approved.'),
    'pretix.event.order.email.order_placed': _(
        'An email has been sent to notify the user that the order has been received and requires payment.'),
    'pretix.event.order.email.order_placed_require_approval': _('An email has been sent to notify the user that '
                                                                'the order has been received and requires '
                                                                'approval.'),
    'pretix.event.order.email.resend': _('An email with a link to the order detail page has been resent to the user.'),
    'pretix.event.order.email.payment_failed': _('An email has been sent to notify the user that the payment failed.'),
})
class CoreOrderLogEntryType(OrderLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.voucher.added': _('The voucher has been created.'),
    'pretix.voucher.sent': _('The voucher has been sent to {recipient}.'),
    'pretix.voucher.expired.waitinglist': _(
        'The voucher has been set to expire because the recipient removed themselves from the waiting list.'),
    'pretix.voucher.changed': _('The voucher has been changed.'),
    'pretix.voucher.deleted': _('The voucher has been deleted.'),
    'pretix.voucher.carts.deleted': _('Cart positions including the voucher have been deleted.'),
    'pretix.voucher.added.waitinglist': _('The voucher has been assigned to {email} through the waiting list.'),
})
class CoreVoucherLogEntryType(VoucherLogEntryType):
    pass


@log_entry_types.new()
class VoucherRedeemedLogEntryType(VoucherLogEntryType):
    action_type = 'pretix.voucher.redeemed'
    plain = _('The voucher has been redeemed in order {order_code}.')

    def display(self, logentry, data):
        url = reverse('control:event.order', kwargs={
            'event': logentry.event.slug,
            'organizer': logentry.event.organizer.slug,
            'code': data.get('order_code', '?')
        })
        return format_html(
            self.plain,
            order_code=format_html('<a href="{}">{}</a>', url, data.get('order_code', '?')),
        )


@log_entry_types.new_from_dict({
    'pretix.event.category.added': _('The category has been added.'),
    'pretix.event.category.deleted': _('The category has been deleted.'),
    'pretix.event.category.changed': _('The category has been changed.'),
    'pretix.event.category.reordered': _('The category has been reordered.'),
})
class CoreItemCategoryLogEntryType(ItemCategoryLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.taxrule.added': _('The tax rule has been added.'),
    'pretix.event.taxrule.deleted': _('The tax rule has been deleted.'),
    'pretix.event.taxrule.changed': _('The tax rule has been changed.'),
})
class CoreTaxRuleLogEntryType(TaxRuleLogEntryType):
    pass


class TeamMembershipLogEntryType(LogEntryType):
    def display(self, logentry, data):
        return self.plain.format(user=data.get('email'))


@log_entry_types.new_from_dict({
    'pretix.team.member.added': _('{user} has been added to the team.'),
    'pretix.team.member.removed': _('{user} has been removed from the team.'),
    'pretix.team.invite.created': _('{user} has been invited to the team.'),
    'pretix.team.invite.resent': _('Invite for {user} has been resent.'),
})
class CoreTeamMembershipLogEntryType(TeamMembershipLogEntryType):
    pass


@log_entry_types.new()
class TeamMemberJoinedLogEntryType(LogEntryType):
    action_type = 'pretix.team.member.joined'

    def display(self, logentry, data):
        return _('{user} has joined the team using the invite sent to {email}.').format(
            user=data.get('email'), email=data.get('invite_email')
        )


@log_entry_types.new()
class UserSettingsChangedLogEntryType(LogEntryType):
    action_type = 'pretix.user.settings.changed'

    def display(self, logentry, data):
        text = str(_('Your account settings have been changed.'))
        if 'email' in data:
            text = text + ' ' + str(
                _('Your email address has been changed to {email}.').format(email=data['email']))
        if 'new_pw' in data:
            text = text + ' ' + str(_('Your password has been changed.'))
        if data.get('is_active') is True:
            text = text + ' ' + str(_('Your account has been enabled.'))
        elif data.get('is_active') is False:
            text = text + ' ' + str(_('Your account has been disabled.'))
        return text


@log_entry_types.new_from_dict({
    'pretix.user.email.changed': _('Your email address has been changed from {old_email} to {email}.'),
    'pretix.user.email.confirmed': _('Your email address {email} has been confirmed.'),
})
class UserEmailChangedLogEntryType(LogEntryType):
    pass


class UserImpersonatedLogEntryType(LogEntryType):
    def display(self, logentry, data):
        return self.plain.format(data['other_email'])


@log_entry_types.new_from_dict({
    'pretix.control.auth.user.impersonated': _('You impersonated {}.'),
    'pretix.control.auth.user.impersonate_stopped': _('You stopped impersonating {}.'),
})
class CoreUserImpersonatedLogEntryType(UserImpersonatedLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.object.cloned': _('This object has been created by cloning.'),
    'pretix.organizer.changed': _('The organizer has been changed.'),
    'pretix.organizer.settings': _('The organizer settings have been changed.'),
    'pretix.organizer.footerlinks.changed': _('The footer links have been changed.'),
    'pretix.organizer.export.schedule.added': _('A scheduled export has been added.'),
    'pretix.organizer.export.schedule.changed': _('A scheduled export has been changed.'),
    'pretix.organizer.export.schedule.deleted': _('A scheduled export has been deleted.'),
    'pretix.organizer.export.schedule.executed': _('A scheduled export has been executed.'),
    'pretix.organizer.export.schedule.failed': _('A scheduled export has failed: {reason}.'),
    'pretix.organizer.outgoingmails.retried': _('Failed emails have been scheduled to be retried.'),
    'pretix.organizer.outgoingmails.aborted': _('Queued emails have been aborted.'),
    'pretix.giftcards.acceptance.added': _('Gift card acceptance for another organizer has been added.'),
    'pretix.giftcards.acceptance.removed': _('Gift card acceptance for another organizer has been removed.'),
    'pretix.giftcards.acceptance.acceptor.invited': _('A new gift card acceptor has been invited.'),
    'pretix.giftcards.acceptance.acceptor.removed': _('A gift card acceptor has been removed.'),
    'pretix.giftcards.acceptance.issuer.removed': _('A gift card issuer has been removed or declined.'),
    'pretix.giftcards.acceptance.issuer.accepted': _('A new gift card issuer has been accepted.'),
    'pretix.webhook.created': _('The webhook has been created.'),
    'pretix.webhook.changed': _('The webhook has been changed.'),
    'pretix.webhook.retries.expedited': _('The webhook call retry jobs have been manually expedited.'),
    'pretix.webhook.retries.dropped': _('The webhook call retry jobs have been dropped.'),
    'pretix.ssoprovider.created': _('The SSO provider has been created.'),
    'pretix.ssoprovider.changed': _('The SSO provider has been changed.'),
    'pretix.ssoprovider.deleted': _('The SSO provider has been deleted.'),
    'pretix.ssoclient.created': _('The SSO client has been created.'),
    'pretix.ssoclient.changed': _('The SSO client has been changed.'),
    'pretix.ssoclient.deleted': _('The SSO client has been deleted.'),
    'pretix.membershiptype.created': _('The membership type has been created.'),
    'pretix.membershiptype.changed': _('The membership type has been changed.'),
    'pretix.membershiptype.deleted': _('The membership type has been deleted.'),
    'pretix.saleschannel.created': _('The sales channel has been created.'),
    'pretix.saleschannel.changed': _('The sales channel has been changed.'),
    'pretix.saleschannel.deleted': _('The sales channel has been deleted.'),
    'pretix.customer.created': _('The account has been created.'),
    'pretix.customer.changed': _('The account has been changed.'),
    'pretix.customer.membership.created': _('A membership for this account has been added.'),
    'pretix.customer.membership.changed': _('A membership of this account has been changed.'),
    'pretix.customer.membership.deleted': _('A membership of this account has been deleted.'),
    'pretix.customer.anonymized': _('The account has been disabled and anonymized.'),
    'pretix.customer.password.resetrequested': _('A new password has been requested.'),
    'pretix.customer.password.set': _('A new password has been set.'),
    'pretix.customer.email.error': _('Sending of an email has failed.'),
    'pretix.reusable_medium.created': _('The reusable medium has been created.'),
    'pretix.reusable_medium.created.auto': _('The reusable medium has been created automatically.'),
    'pretix.reusable_medium.changed': _('The reusable medium has been changed.'),
    'pretix.reusable_medium.linked_orderposition.changed': _('The medium has been connected to a new ticket.'),
    'pretix.reusable_medium.linked_giftcard.changed': _('The medium has been connected to a new gift card.'),
    'pretix.email.error': _('Sending of an email has failed.'),
    'pretix.event.comment': _('The event\'s internal comment has been updated.'),
    'pretix.event.canceled': _('The event has been canceled.'),
    'pretix.event.deleted': _('An event has been deleted.'),
    'pretix.event.shredder.started': _('A removal process for personal data has been started.'),
    'pretix.event.shredder.completed': _('A removal process for personal data has been completed.'),
    'pretix.event.export.schedule.added': _('A scheduled export has been added.'),
    'pretix.event.export.schedule.changed': _('A scheduled export has been changed.'),
    'pretix.event.export.schedule.deleted': _('A scheduled export has been deleted.'),
    'pretix.event.export.schedule.executed': _('A scheduled export has been executed.'),
    'pretix.event.export.schedule.failed': _('A scheduled export has failed: {reason}.'),
    'pretix.control.auth.user.created': _('The user has been created.'),
    'pretix.control.auth.user.new_source': _('A first login using {agent_type} on {os_type} from {country} has '
                                             'been detected.'),
    'pretix.user.settings.2fa.enabled': _('Two-factor authentication has been enabled.'),
    'pretix.user.settings.2fa.disabled': _('Two-factor authentication has been disabled.'),
    'pretix.user.settings.2fa.regenemergency': _('Your two-factor emergency codes have been regenerated.'),
    'pretix.user.settings.2fa.emergency': _('A two-factor emergency code has been generated.'),
    'pretix.user.settings.2fa.device.added': _('A new two-factor authentication device "{name}" has been added to '
                                               'your account.'),
    'pretix.user.settings.2fa.device.deleted': _('The two-factor authentication device "{name}" has been removed '
                                                 'from your account.'),
    'pretix.user.settings.notifications.enabled': _('Notifications have been enabled.'),
    'pretix.user.settings.notifications.disabled': _('Notifications have been disabled.'),
    'pretix.user.settings.notifications.changed': _('Your notification settings have been changed.'),
    'pretix.user.anonymized': _('This user has been anonymized.'),
    'pretix.user.oauth.authorized': _('The application "{application_name}" has been authorized to access your '
                                      'account.'),
    'pretix.user.email.error': _('Sending of an email has failed.'),
    'pretix.control.auth.user.forgot_password.mail_sent': _('Password reset mail sent.'),
    'pretix.control.auth.user.forgot_password.recovered': _('The password has been reset.'),
    'pretix.control.auth.user.forgot_password.denied.repeated': _('A repeated password reset has been denied, as '
                                                                  'the last request was less than 24 hours ago.'),
    'pretix.organizer.deleted': _('The organizer "{name}" has been deleted.'),
    'pretix.waitinglist.voucher': _('A voucher has been sent to a person on the waiting list.'),  # legacy
    'pretix.event.order.waitinglist.transferred': _('An entry has been transferred to another waiting list.'),  # legacy
    'pretix.team.created': _('The team has been created.'),
    'pretix.team.changed': _('The team settings have been changed.'),
    'pretix.team.deleted': _('The team has been deleted.'),
    'pretix.gate.created': _('The gate has been created.'),
    'pretix.gate.changed': _('The gate has been changed.'),
    'pretix.gate.deleted': _('The gate has been deleted.'),
    'pretix.subevent.deleted': pgettext_lazy('subevent', 'The event date has been deleted.'),
    'pretix.subevent.canceled': pgettext_lazy('subevent', 'The event date has been canceled.'),
    'pretix.subevent.changed': pgettext_lazy('subevent', 'The event date has been changed.'),
    'pretix.subevent.added': pgettext_lazy('subevent', 'The event date has been created.'),
    'pretix.subevent.quota.added': pgettext_lazy('subevent', 'A quota has been added to the event date.'),
    'pretix.subevent.quota.changed': pgettext_lazy('subevent', 'A quota has been changed on the event date.'),
    'pretix.subevent.quota.deleted': pgettext_lazy('subevent', 'A quota has been removed from the event date.'),
    'pretix.device.created': _('The device has been created.'),
    'pretix.device.changed': _('The device has been changed.'),
    'pretix.device.revoked': _('Access of the device has been revoked.'),
    'pretix.device.initialized': _('The device has been initialized.'),
    'pretix.device.keyroll': _('The access token of the device has been regenerated.'),
    'pretix.device.updated': _('The device has notified the server of an hardware or software update.'),
    'pretix.giftcards.created': _('The gift card has been created.'),
    'pretix.giftcards.modified': _('The gift card has been changed.'),
    'pretix.giftcards.transaction.manual': _('A manual transaction has been performed.'),
    'pretix.giftcards.transaction.payment': _('A payment has been performed.'),
    'pretix.giftcards.transaction.refund': _('A refund has been performed. '),
    'pretix.team.token.created': _('The token "{name}" has been created.'),
    'pretix.team.token.deleted': _('The token "{name}" has been revoked.'),
    'pretix.event.checkin.reset': _('The check-in and print log state has been reset.')
})
class CoreLogEntryType(LogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.organizer.plugins.enabled': _('The plugin has been enabled.'),
    'pretix.organizer.plugins.disabled': _('The plugin has been disabled.'),
})
class OrganizerPluginStateLogEntryType(LogEntryType):
    object_link_wrapper = _('Plugin {val}')

    def get_object_link_info(self, logentry) -> Optional[dict]:
        if 'plugin' in logentry.parsed_data:
            app = app_cache.get(logentry.parsed_data['plugin'])
            if app and hasattr(app, 'PretixPluginMeta'):
                return {
                    'href': reverse('control:organizer.settings.plugins', kwargs={
                        'organizer': logentry.organizer.slug,
                    }) + '#plugin_' + logentry.parsed_data['plugin'],
                    'val': app.PretixPluginMeta.name
                }


@log_entry_types.new_from_dict({
    'pretix.event.item_meta_property.added': _('A meta property has been added to this event.'),
    'pretix.event.item_meta_property.deleted': _('A meta property has been removed from this event.'),
    'pretix.event.item_meta_property.changed': _('A meta property has been changed on this event.'),
    'pretix.event.settings': _('The event settings have been changed.'),
    'pretix.event.tickets.settings': _('The ticket download settings have been changed.'),
    'pretix.event.tickets.provider': _('The settings of a ticket output provider have been changed.'),
    'pretix.event.payment.provider': _('The settings of a payment provider have been changed.'),
    'pretix.event.live.activated': _('The shop has been taken live.'),
    'pretix.event.live.deactivated': _('The shop has been taken offline.'),
    'pretix.event.testmode.activated': _('The shop has been taken into test mode.'),
    'pretix.event.testmode.deactivated': _('The test mode has been disabled.'),
    'pretix.event.added': _('The event has been created.'),
    'pretix.event.changed': _('The event details have been changed.'),
    'pretix.event.footerlinks.changed': _('The footer links have been changed.'),
    'pretix.event.question.option.added': _('An answer option has been added to the question.'),
    'pretix.event.question.option.deleted': _('An answer option has been removed from the question.'),
    'pretix.event.question.option.changed': _('An answer option has been changed.'),
    'pretix.event.permissions.added': _('A user has been added to the event team.'),
    'pretix.event.permissions.invited': _('A user has been invited to the event team.'),
    'pretix.event.permissions.changed': _('A user\'s permissions have been changed.'),
    'pretix.event.permissions.deleted': _('A user has been removed from the event team.'),
})
class CoreEventLogEntryType(EventLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.checkinlist.added': _('The check-in list has been added.'),
    'pretix.event.checkinlist.deleted': _('The check-in list has been deleted.'),
    'pretix.event.checkinlists.deleted': _('The check-in list has been deleted.'),  # backwards compatibility
    'pretix.event.checkinlist.changed': _('The check-in list has been changed.'),
})
class CheckinlistLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Check-in list {val}')
    object_link_viewname = 'control:event.orders.checkinlists.edit'
    object_link_argname = 'list'
    content_type = CheckinList


@log_entry_types.new_from_dict({
    'pretix.event.plugins.enabled': _('The plugin has been enabled.'),
    'pretix.event.plugins.disabled': _('The plugin has been disabled.'),
})
class EventPluginStateLogEntryType(EventLogEntryType):
    object_link_wrapper = _('Plugin {val}')

    def get_object_link_info(self, logentry) -> Optional[dict]:
        if 'plugin' in logentry.parsed_data:
            app = app_cache.get(logentry.parsed_data['plugin'])
            if app and hasattr(app, 'PretixPluginMeta'):
                return {
                    'href': reverse('control:event.settings.plugins', kwargs={
                        'organizer': logentry.event.organizer.slug,
                        'event': logentry.event.slug,
                    }) + '#plugin_' + logentry.parsed_data['plugin'],
                    'val': app.PretixPluginMeta.name
                }


@log_entry_types.new_from_dict({
    'pretix.event.item.added': _('The product has been created.'),
    'pretix.event.item.changed': _('The product has been changed.'),
    'pretix.event.item.reordered': _('The product has been reordered.'),
    'pretix.event.item.deleted': _('The product has been deleted.'),
    'pretix.event.item.addons.added': _('An add-on has been added to this product.'),
    'pretix.event.item.addons.removed': _('An add-on has been removed from this product.'),
    'pretix.event.item.addons.changed': _('An add-on has been changed on this product.'),
    'pretix.event.item.bundles.added': _('A bundled item has been added to this product.'),
    'pretix.event.item.bundles.removed': _('A bundled item has been removed from this product.'),
    'pretix.event.item.bundles.changed': _('A bundled item has been changed on this product.'),
    'pretix.event.item.program_times.added': _('A program time has been added to this product.'),
    'pretix.event.item.program_times.changed': _('A program time has been changed on this product.'),
    'pretix.event.item.program_times.removed': _('A program time has been removed from this product.'),
})
class CoreItemLogEntryType(ItemLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.item.variation.added': _('The variation "{value}" has been created.'),
    'pretix.event.item.variation.deleted': _('The variation "{value}" has been deleted.'),
    'pretix.event.item.variation.changed': _('The variation "{value}" has been changed.'),
})
class VariationLogEntryType(ItemLogEntryType):
    def display(self, logentry, data):
        if 'value' not in data:
            # Backwards compatibility
            var = ItemVariation.objects.filter(id=data['id']).first()
            if var:
                data['value'] = str(var.value)
            else:
                data['value'] = '?'
        else:
            data['value'] = LazyI18nString(data['value'])
        return super().display(logentry, data)


@log_entry_types.new_from_dict({
    'pretix.event.order.payment.confirmed': _('Payment {local_id} has been confirmed.'),
    'pretix.event.order.payment.canceled': _('Payment {local_id} has been canceled.'),
    'pretix.event.order.payment.canceled.failed': _('Canceling payment {local_id} has failed.'),
    'pretix.event.order.payment.started': _('Payment {local_id} has been started.'),
    'pretix.event.order.payment.failed': _('Payment {local_id} has failed.'),
    'pretix.event.order.quotaexceeded': _('The order could not be marked as paid: {message}'),
    'pretix.event.order.overpaid': _('The order has been overpaid.'),
    'pretix.event.order.refund.created': _('Refund {local_id} has been created.'),
    'pretix.event.order.refund.created.externally': _('Refund {local_id} has been created by an external entity.'),
    'pretix.event.order.refund.requested': _('The customer requested you to issue a refund.'),
    'pretix.event.order.refund.done': _('Refund {local_id} has been completed.'),
    'pretix.event.order.refund.canceled': _('Refund {local_id} has been canceled.'),
    'pretix.event.order.refund.failed': _('Refund {local_id} has failed.'),
})
class CoreOrderPaymentLogEntryType(OrderLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.quota.added': _('The quota has been added.'),
    'pretix.event.quota.deleted': _('The quota has been deleted.'),
    'pretix.event.quota.changed': _('The quota has been changed.'),
    'pretix.event.quota.closed': _('The quota has closed.'),
    'pretix.event.quota.opened': _('The quota has been re-opened.'),
})
class CoreQuotaLogEntryType(QuotaLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.question.added': _('The question has been added.'),
    'pretix.event.question.deleted': _('The question has been deleted.'),
    'pretix.event.question.changed': _('The question has been changed.'),
    'pretix.event.question.reordered': _('The question has been reordered.'),
})
class CoreQuestionLogEntryType(QuestionLogEntryType):
    pass


@log_entry_types.new_from_dict({
    'pretix.event.discount.added': _('The discount has been added.'),
    'pretix.event.discount.deleted': _('The discount has been deleted.'),
    'pretix.event.discount.changed': _('The discount has been changed.'),
})
class CoreDiscountLogEntryType(DiscountLogEntryType):
    pass


@log_entry_types.new()
class LegacyCheckinLogEntryType(OrderLogEntryType):
    action_type = 'pretix.control.views.checkin'

    def display(self, logentry, data):
        # deprecated
        dt = dateutil.parser.parse(data.get('datetime'))
        tz = logentry.event.timezone
        dt_formatted = date_format(dt.astimezone(tz), "SHORT_DATETIME_FORMAT")
        if 'list' in data:
            try:
                checkin_list = logentry.event.checkin_lists.get(pk=data.get('list')).name
            except CheckinList.DoesNotExist:
                checkin_list = _("(unknown)")
        else:
            checkin_list = _("(unknown)")

        if data.get('first'):
            return _('Position #{posid} has been checked in manually at {datetime} on list "{list}".').format(
                posid=data.get('positionid'),
                datetime=dt_formatted,
                list=checkin_list,
            )
        return _('Position #{posid} has been checked in again at {datetime} on list "{list}".').format(
            posid=data.get('positionid'),
            datetime=dt_formatted,
            list=checkin_list
        )


@log_entry_types.new_from_dict({
    'pretix.event.orders.waitinglist.voucher_assigned': _('A voucher has been sent to a person on the waiting list.'),
    'pretix.event.orders.waitinglist.deleted': _('An entry has been removed from the waiting list.'),
    'pretix.event.orders.waitinglist.changed': _('An entry has been changed on the waiting list.'),
    'pretix.event.orders.waitinglist.added': _('An entry has been added to the waiting list.'),
})
class CoreWaitingListEntryLogEntryType(WaitingListEntryLogEntryType):
    pass
