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
import logging
from collections import OrderedDict

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.api.signals import register_device_security_profile

logger = logging.getLogger(__name__)
_ALL_PROFILES = None


class BaseSecurityProfile:
    @property
    def identifier(self) -> str:
        """
        Unique identifier for this profile.
        """
        raise NotImplementedError()

    @property
    def verbose_name(self) -> str:
        """
        Human-readable name (can be a ``gettext_lazy`` object).
        """
        raise NotImplementedError()

    def is_allowed(self, request) -> bool:
        """
        Return whether a given request should be allowed.
        """
        raise NotImplementedError()


class FullAccessSecurityProfile(BaseSecurityProfile):
    identifier = 'full'
    verbose_name = _('Full device access (reading and changing orders and gift cards, reading of products and settings)')

    def is_allowed(self, request):
        return True


class AllowListSecurityProfile(BaseSecurityProfile):
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
        ('POST', 'api-v1:orderposition-printlog'),
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
        ('POST', 'api-v1:orderposition-printlog'),
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
        ('POST', 'api-v1:orderposition-printlog'),
        ('GET', 'api-v1:event.settings'),
        ('POST', 'api-v1:upload'),
        ('POST', 'api-v1:checkinrpc.redeem'),
        ('GET', 'api-v1:checkinrpc.search'),
    )


def get_all_security_profiles():
    global _ALL_PROFILES

    if _ALL_PROFILES:
        return _ALL_PROFILES

    types = OrderedDict()
    for recv, ret in register_device_security_profile.send(None):
        if isinstance(ret, (list, tuple)):
            for r in ret:
                types[r.identifier] = r
        else:
            types[ret.identifier] = ret
    _ALL_PROFILES = types
    return types


@receiver(register_device_security_profile, dispatch_uid="base_register_default_security_profiles")
def register_default_webhook_events(sender, **kwargs):
    return (
        FullAccessSecurityProfile(),
        PretixScanSecurityProfile(),
        PretixScanNoSyncSecurityProfile(),
        PretixScanNoSyncNoSearchSecurityProfile(),
    )
