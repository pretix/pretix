from django.urls import path
from . import views

urlpatterns = [
    path('control/event/<str:organizer>/<str:event>/zalozns/settings',
         views.ZaloZNSSettings.as_view(), name='settings'),
    path('control/event/<str:organizer>/<str:event>/order/<str:order>/zalozns/send',
         views.ZaloZNSSendView.as_view(), name='send'),
]
