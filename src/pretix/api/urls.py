from django.conf.urls import include, url
from rest_framework import routers

from .views import event, item, organizer

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)

orga_router = routers.DefaultRouter()
orga_router.register(r'events', event.EventViewSet)

event_router = routers.DefaultRouter()
event_router.register(r'items', item.ItemViewSet)
event_router.register(r'categories', item.ItemCategoryViewSet)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/', include(orga_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/', include(event_router.urls)),
]
