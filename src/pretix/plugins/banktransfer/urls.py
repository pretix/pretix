from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/import/', views.ImportView.as_view(),
        name='import'),
]
