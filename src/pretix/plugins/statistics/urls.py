from django.conf.urls import re_path

from . import views

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/statistics/', views.IndexView.as_view(),
            name='index'),
]
