from django.utils.translation import ugettext_lazy as _


class FullAccessSecurityProfile:
    identifier = 'full'
    verbose_name = _('Full device access (reading and changing orders and gift cards, reading of products and settings)')

    def is_allowed(self, request):
        return True


class AllowListSecurityProfile:
    allowlist = tuple()

    def is_allowed(self, request):
        key = (request.method, f"{request.resolver_match.namespace}:{request.resolver_match.url_name}")
        return key in self.allowlist


class PretixScanSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixscan'
    verbose_name = _('pretixSCAN')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.update'),
        ('GET', 'api-v1:device.revoke'),
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
        ('GET', 'api-v1:checkinlistpos-list'),
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:order-list'),
        ('GET', 'api-v1:event.settings'),
    )


class PretixScanNoSyncSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixscan_online_kiosk'
    verbose_name = _('pretixSCAN (kiosk mode, online only)')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.update'),
        ('GET', 'api-v1:device.revoke'),
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
        ('POST', 'api-v1:checkinlistpos-redeem'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:event.settings'),
    )


class PretixPosSecurityProfile(AllowListSecurityProfile):
    identifier = 'pretixpos'
    verbose_name = _('pretixPOS')
    allowlist = (
        ('GET', 'api-v1:version'),
        ('GET', 'api-v1:device.update'),
        ('GET', 'api-v1:device.revoke'),
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
        ('GET', 'api-v1:order-list'),
        ('POST', 'api-v1:order-list'),
        ('GET', 'api-v1:order-detail'),
        ('DELETE', 'api-v1:orderposition-detail'),
        ('POST', 'api-v1:order-mark_canceled'),
        ('POST', 'api-v1:orderrefund-list'),
        ('POST', 'api-v1:orderrefund-done'),
        ('POST', 'api-v1:cartposition-list'),
        ('DELETE', 'api-v1:cartposition-detail'),
        ('GET', 'api-v1:giftcard-list'),
        ('POST', 'api-v1:giftcard-transact'),
        ('POST', 'plugins:pretix_posbackend:posreceipt-list'),
        ('POST', 'plugins:pretix_posbackend:posclosing-list'),
        ('POST', 'plugins:pretix_posbackend:posdebugdump-list'),
        ('POST', 'plugins:pretix_posbackend:stripeterminal.token'),
        ('GET', 'api-v1:revokedsecrets-list'),
        ('GET', 'api-v1:event.settings'),
    )


DEVICE_SECURITY_PROFILES = {
    k.identifier: k() for k in (
        FullAccessSecurityProfile,
        PretixScanSecurityProfile,
        PretixScanNoSyncSecurityProfile,
        PretixPosSecurityProfile,
    )
}
