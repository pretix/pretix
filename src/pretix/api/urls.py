from django.conf.urls import include, url
from rest_framework import routers

from .views import item, organizer

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)

event_router = routers.DefaultRouter()
event_router.register(r'items', item.ItemViewSet)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^events/(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(event_router.urls)),
]
