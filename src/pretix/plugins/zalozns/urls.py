from django.urls import path
from . import views

urlpatterns = [
    path('control/event/<str:organizer>/<str:event>/zalozns/settings',
         views.ZaloZNSSettings.as_view(), name='settings'),
]
