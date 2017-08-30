from django.conf.urls import include, url

from . import views

pretixdroid_api_patterns = [
    url(r'^redeem/', views.ApiRedeemView.as_view(),
        name='api.redeem'),
    url(r'^search/', views.ApiSearchView.as_view(),
        name='api.search'),
    url(r'^download/', views.ApiDownloadView.as_view(),
        name='api.download'),
    url(r'^status/', views.ApiStatusView.as_view(),
        name='api.status'),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pretixdroid/$', views.ConfigView.as_view(),
        name='config'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pretixdroid/(?P<config>\d+)/$',
        views.ConfigCodeView.as_view(), name='config.code'),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/(?P<subevent>\d+)/',
        include(pretixdroid_api_patterns)),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(pretixdroid_api_patterns)),
]
