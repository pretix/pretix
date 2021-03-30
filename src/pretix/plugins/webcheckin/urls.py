from django.conf.urls import url

from .views import IndexView

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/webcheckin/$',
        IndexView.as_view(), name='index'),
]
