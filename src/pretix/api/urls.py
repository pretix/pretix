from django.conf.urls import include, url
from rest_framework import routers

from .views import event

router = routers.DefaultRouter()
router.register(r'events', event.EventViewSet)

urlpatterns = [
    url(r'^', include(router.urls)),
]
