from django.conf.urls import include, url

from pretix.multidomain import event_url

from .views import (
    OrganizerSettingsFormView, ReturnView, ScaReturnView, ScaView,
    applepay_association, oauth_connect, oauth_disconnect, oauth_return,
    redirect_view, webhook,
)

event_patterns = [
    url(r'^stripe/', include([
        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
        url(r'^redirect/$', redirect_view, name='redirect'),
        url(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$', ReturnView.as_view(), name='return'),
        url(r'^sca/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$', ScaView.as_view(), name='sca'),
        url(r'^sca/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/return/$',
            ScaReturnView.as_view(), name='sca.return'),
    ])),
    url(r'^.well-known/apple-developer-merchantid-domain-association$',
        applepay_association, name='applepay.association'),
]

organizer_patterns = [
    url(r'^.well-known/apple-developer-merchantid-domain-association$',
        applepay_association, name='applepay.association'),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/disconnect/',
        oauth_disconnect, name='oauth.disconnect'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/stripe/connect/',
        oauth_connect, name='oauth.connect'),
    url(r'^control/organizer/(?P<organizer>[^/]+)/stripeconnect/',
        OrganizerSettingsFormView.as_view(), name='settings.connect'),
    url(r'^_stripe/webhook/$', webhook, name='webhook'),
    url(r'^_stripe/oauth_return/$', oauth_return, name='oauth.return'),
    url(r'^.well-known/apple-developer-merchantid-domain-association$',
        applepay_association, name='applepay.association'),
]
