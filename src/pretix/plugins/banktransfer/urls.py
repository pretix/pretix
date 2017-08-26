from django.conf.urls import url

from pretix.api.urls import orga_router
from pretix.plugins.banktransfer.api import BankImportJobViewSet

from . import views

urlpatterns = [
    url(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/import/',
        views.OrganizerImportView.as_view(),
        name='import'),
    url(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/job/(?P<job>\d+)/',
        views.OrganizerJobDetailView.as_view(), name='import.job'),
    url(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/action/',
        views.OrganizerActionView.as_view(), name='import.action'),

    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/import/',
        views.EventImportView.as_view(),
        name='import'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/job/(?P<job>\d+)/',
        views.EventJobDetailView.as_view(), name='import.job'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/action/',
        views.EventActionView.as_view(), name='import.action'),
]

orga_router.register('bankimportjobs', BankImportJobViewSet)
