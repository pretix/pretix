#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
import logging

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class FullAccessSecurityProfile:
    identifier = 'full'
    verbose_name = _('Full device access (reading and changing orders and gift cards, reading of products and settings)')

    def is_allowed(self, request):
        return True


class AllowListSecurityProfile:
    allowlist = ()

    def is_allowed(self, request):
        key = (request.method, f"{request.resolver_match.namespace}:{request.resolver_match.url_name}")
        if key in self.allowlist:
            return True
        else:
            logger.info(
                f'Request {key} not allowed in profile {self.identifier}'
            )
            return False


class PretixScanSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixscan'
    verbose_name = _('pretixSCAN')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.eventselection'),
        ('GET', 'api-v1:idempotency.query'),
        ('GET', 'api-v1:device.info'),
        ('POST', 'api-v1:device.update'),
        ('POST', 'api-v1:device.revoke'),
        ('POST', 'api-v1:device.roll'),
        ('GET', 'api-v1:event-list'),
        ('GET', 'api-v1:event-detail'),
        ('GET', 'api-v1:subevent-list'),
        ('GET', 'api-v1:subevent-detail'),
        ('GET', 'api-v1:itemcategory-list'),
        ('GET', 'api-v1:item-list'),
        ('GET', 'api-v1:question-list'),
        ('GET', 'api-v1:badgelayout-list'),
        ('GET', 'api-v1:badgeitem-list'),
        ('GET', 'api-v1:checkinlist-list'),
        ('GET', 'api-v1:checkinlist-status'),
        ('POST', 'api-v1:checkinlist-failed_checkins'),
        ('GET', 'api-v1:checkinlistpos-list'),
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:blockedsecrets-list'),
        ('GET', 'api-v1:order-list'),
        ('GET', 'api-v1:orderposition-pdf_image'),
        ('GET', 'api-v1:event.settings'),
        ('POST', 'api-v1:upload'),
        ('POST', 'api-v1:checkinrpc.redeem'),
        ('GET', 'api-v1:checkinrpc.search'),
        ('GET', 'api-v1:reusablemedium-list'),
    )


class PretixScanNoSyncNoSearchSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixscan_online_kiosk'
    verbose_name = _('pretixSCAN (kiosk mode, no order sync, no search)')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.eventselection'),
        ('GET', 'api-v1:idempotency.query'),
        ('GET', 'api-v1:device.info'),
        ('POST', 'api-v1:device.update'),
        ('POST', 'api-v1:device.revoke'),
        ('POST', 'api-v1:device.roll'),
        ('GET', 'api-v1:event-list'),
        ('GET', 'api-v1:event-detail'),
        ('GET', 'api-v1:subevent-list'),
        ('GET', 'api-v1:subevent-detail'),
        ('GET', 'api-v1:itemcategory-list'),
        ('GET', 'api-v1:item-list'),
        ('GET', 'api-v1:question-list'),
        ('GET', 'api-v1:badgelayout-list'),
        ('GET', 'api-v1:badgeitem-list'),
        ('GET', 'api-v1:checkinlist-list'),
        ('GET', 'api-v1:checkinlist-status'),
        ('POST', 'api-v1:checkinlist-failed_checkins'),
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:blockedsecrets-list'),
        ('GET', 'api-v1:orderposition-pdf_image'),
        ('GET', 'api-v1:event.settings'),
        ('POST', 'api-v1:upload'),
        ('POST', 'api-v1:checkinrpc.redeem'),
        ('GET', 'api-v1:checkinrpc.search'),
    )


class PretixScanNoSyncSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixscan_online_noorders'
    verbose_name = _('pretixSCAN (online only, no order sync)')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.eventselection'),
        ('GET', 'api-v1:idempotency.query'),
        ('GET', 'api-v1:device.info'),
        ('POST', 'api-v1:device.update'),
        ('POST', 'api-v1:device.revoke'),
        ('POST', 'api-v1:device.roll'),
        ('GET', 'api-v1:event-list'),
        ('GET', 'api-v1:event-detail'),
        ('GET', 'api-v1:subevent-list'),
        ('GET', 'api-v1:subevent-detail'),
        ('GET', 'api-v1:itemcategory-list'),
        ('GET', 'api-v1:item-list'),
        ('GET', 'api-v1:question-list'),
        ('GET', 'api-v1:badgelayout-list'),
        ('GET', 'api-v1:badgeitem-list'),
        ('GET', 'api-v1:checkinlist-list'),
        ('GET', 'api-v1:checkinlist-status'),
        ('POST', 'api-v1:checkinlist-failed_checkins'),
        ('GET', 'api-v1:checkinlistpos-list'),
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:blockedsecrets-list'),
        ('GET', 'api-v1:orderposition-pdf_image'),
        ('GET', 'api-v1:event.settings'),
        ('POST', 'api-v1:upload'),
        ('POST', 'api-v1:checkinrpc.redeem'),
        ('GET', 'api-v1:checkinrpc.search'),
    )


class PretixPosSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixpos'
    verbose_name = _('pretixPOS')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.eventselection'),
        ('GET', 'api-v1:idempotency.query'),
        ('GET', 'api-v1:device.info'),
        ('POST', 'api-v1:device.update'),
        ('POST', 'api-v1:device.revoke'),
        ('POST', 'api-v1:device.roll'),
        ('GET', 'api-v1:event-list'),
        ('GET', 'api-v1:event-detail'),
        ('GET', 'api-v1:subevent-list'),
        ('GET', 'api-v1:subevent-detail'),
        ('GET', 'api-v1:itemcategory-list'),
        ('GET', 'api-v1:item-list'),
        ('GET', 'api-v1:question-list'),
        ('GET', 'api-v1:quota-list'),
        ('GET', 'api-v1:taxrule-list'),
        ('GET', 'api-v1:ticketlayout-list'),
        ('GET', 'api-v1:ticketlayoutitem-list'),
        ('GET', 'api-v1:badgelayout-list'),
        ('GET', 'api-v1:badgeitem-list'),
        ('GET', 'api-v1:voucher-list'),
        ('GET', 'api-v1:voucher-detail'),
        ('GET', 'api-v1:order-list'),
        ('POST', 'api-v1:order-list'),
        ('GET', 'api-v1:order-detail'),
        ('DELETE', 'api-v1:orderposition-detail'),
        ('PATCH', 'api-v1:orderposition-detail'),
        ('GET', 'api-v1:orderposition-answer'),
        ('GET', 'api-v1:orderposition-pdf_image'),
        ('POST', 'api-v1:order-mark-canceled'),
        ('POST', 'api-v1:orderpayment-list'),
        ('POST', 'api-v1:orderrefund-list'),
        ('POST', 'api-v1:orderrefund-done'),
        ('POST', 'api-v1:cartposition-list'),
        ('POST', 'api-v1:cartposition-bulk-create'),
        ('GET', 'api-v1:checkinlist-list'),
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('POST', 'plugins:pretix_posbackend:order.posprintlog'),
        ('POST', 'plugins:pretix_posbackend:order.poslock'),
        ('DELETE', 'plugins:pretix_posbackend:order.poslock'),
        ('DELETE', 'api-v1:cartposition-detail'),
        ('GET', 'api-v1:giftcard-list'),
        ('POST', 'api-v1:giftcard-transact'),
        ('PATCH', 'api-v1:giftcard-detail'),
        ('GET', 'plugins:pretix_posbackend:posclosing-list'),
        ('POST', 'plugins:pretix_posbackend:posreceipt-list'),
        ('POST', 'plugins:pretix_posbackend:posclosing-list'),
        ('POST', 'plugins:pretix_posbackend:posdebugdump-list'),
        ('POST', 'plugins:pretix_posbackend:posdebuglogentry-list'),
        ('POST', 'plugins:pretix_posbackend:posdebuglogentry-bulk-create'),
        ('GET', 'plugins:pretix_posbackend:poscashier-list'),
        ('POST', 'plugins:pretix_posbackend:stripeterminal.token'),
        ('POST', 'plugins:pretix_posbackend:stripeterminal.paymentintent'),
        ('PUT', 'plugins:pretix_posbackend:file.upload'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:blockedsecrets-list'),
        ('GET', 'api-v1:event.settings'),
        ('GET', 'plugins:pretix_seating:event.event'),
        ('GET', 'plugins:pretix_seating:event.event.subevent'),
        ('GET', 'plugins:pretix_seating:event.plan'),
        ('GET', 'plugins:pretix_seating:selection.simple'),
        ('POST', 'api-v1:upload'),
        ('POST', 'api-v1:checkinrpc.redeem'),
        ('GET', 'api-v1:checkinrpc.search'),
        ('POST', 'api-v1:reusablemedium-lookup'),
        ('POST', 'api-v1:reusablemedium-list'),
    )


DEVICE_SECURITY_PROFILES = {
    k.identifier: k() for k in (
        FullAccessSecurityProfile,
        PretixScanSecurityProfile,
        PretixScanNoSyncSecurityProfile,
        PretixScanNoSyncNoSearchSecurityProfile,
        PretixPosSecurityProfile,
    )
}
