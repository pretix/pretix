from django.conf.urls import include, re_path

from pretix.multidomain import event_url

from .views import (
    abort, oauth_disconnect, oauth_return, redirect_view, success, webhook,
)

event_patterns = [
    re_path(r'^paypal/', include([
        re_path(r'^abort/$', abort, name='abort'),
        re_path(r'^return/$', success, name='return'),
        re_path(r'^redirect/$', redirect_view, name='redirect'),

        re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/abort/', abort, name='abort'),
        re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/return/', success, name='return'),

        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
    ])),
]

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/paypal/disconnect/',
            oauth_disconnect, name='oauth.disconnect'),
    re_path(r'^_paypal/webhook/$', webhook, name='webhook'),
    re_path(r'^_paypal/oauth_return/$', oauth_return, name='oauth.return'),
]
