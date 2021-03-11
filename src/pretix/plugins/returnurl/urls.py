from django.conf.urls import re_path

from .views import ReturnSettings

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/returnurl/settings$',
            ReturnSettings.as_view(), name='settings'),
]
