from django.conf.urls import url

from .views import ReturnSettings

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/returnurl/settings$',
        ReturnSettings.as_view(), name='settings'),
]
