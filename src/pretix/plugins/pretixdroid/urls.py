from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pretixdroid/', views.ConfigView.as_view(),
        name='config'),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/redeem/', views.ApiRedeemView.as_view(),
        name='api.redeem'),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/search/', views.ApiSearchView.as_view(),
        name='api.search'),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/status/', views.ApiStatusView.as_view(),
        name='api.status'),
]
