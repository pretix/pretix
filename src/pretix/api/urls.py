from django.conf.urls import include, url
from rest_framework import routers

from .views import event, organizer

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)
router.register(r'events', event.EventViewSet)


urlpatterns = [
    url(r'^', include(router.urls)),
]
