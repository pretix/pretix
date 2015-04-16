from django.conf.urls import url

from .views import *


urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/import/', ImportView.as_view(),
        name='import'),
]
