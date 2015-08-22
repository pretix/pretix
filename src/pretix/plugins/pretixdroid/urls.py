from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pretixdroid/', views.ConfigView.as_view(),
        name='config'),
    url(r'^pretixdroid/api/(?P<organizer>[^/]+)/(?P<event>[^/]+)/', views.ApiView.as_view(),
        name='api'),
]
