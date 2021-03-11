from django.conf.urls import include, re_path

from pretix.multidomain import event_url

from .views import (
    OrganizerSettingsFormView, ReturnView, ScaReturnView, ScaView,
    applepay_association, oauth_disconnect, oauth_return, redirect_view,
    webhook,
)

event_patterns = [
    re_path(r'^stripe/', include([
        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
        re_path(r'^redirect/$', redirect_view, name='redirect'),
        re_path(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$', ReturnView.as_view(), name='return'),
        re_path(r'^sca/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$', ScaView.as_view(), name='sca'),
        re_path(r'^sca/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/return/$',
                ScaReturnView.as_view(), name='sca.return'),
    ])),
    re_path(r'^.well-known/apple-developer-merchantid-domain-association$',
            applepay_association, name='applepay.association'),
]

organizer_patterns = [
    re_path(r'^.well-known/apple-developer-merchantid-domain-association$',
            applepay_association, name='applepay.association'),
]

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/disconnect/',
            oauth_disconnect, name='oauth.disconnect'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/stripeconnect/',
            OrganizerSettingsFormView.as_view(), name='settings.connect'),
    re_path(r'^_stripe/webhook/$', webhook, name='webhook'),
    re_path(r'^_stripe/oauth_return/$', oauth_return, name='oauth.return'),
    re_path(r'^.well-known/apple-developer-merchantid-domain-association$',
            applepay_association, name='applepay.association'),
]
