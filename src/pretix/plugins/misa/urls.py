from django.urls import path
from . import views

urlpatterns = [
    path('control/event/<str:organizer>/<str:event>/misa/settings',
         views.MisaSettings.as_view(), name='settings'),
    path('control/event/<str:organizer>/<str:event>/misa/history',
         views.MisaHistoryView.as_view(), name='history'),
]
