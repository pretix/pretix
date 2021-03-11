from django.conf.urls import re_path

from pretix.api.urls import orga_router
from pretix.plugins.banktransfer.api import BankImportJobViewSet

from . import views

urlpatterns = [
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/import/',
            views.OrganizerImportView.as_view(),
            name='import'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/job/(?P<job>\d+)/',
            views.OrganizerJobDetailView.as_view(), name='import.job'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/action/',
            views.OrganizerActionView.as_view(), name='import.action'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/refunds/',
            views.OrganizerRefundExportListView.as_view(), name='refunds.list'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/export/(?P<id>\d+)/$',
            views.OrganizerDownloadRefundExportView.as_view(),
            name='refunds.download'),
    re_path(r'^control/organizer/(?P<organizer>[^/]+)/banktransfer/sepa-export/(?P<id>\d+)/$',
            views.OrganizerSepaXMLExportView.as_view(),
            name='refunds.sepa'),

    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/import/',
            views.EventImportView.as_view(),
            name='import'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/job/(?P<job>\d+)/',
            views.EventJobDetailView.as_view(), name='import.job'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/action/',
            views.EventActionView.as_view(), name='import.action'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/refunds/',
            views.EventRefundExportListView.as_view(),
            name='refunds.list'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/export/(?P<id>\d+)/$',
            views.EventDownloadRefundExportView.as_view(),
            name='refunds.download'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/banktransfer/sepa-export/(?P<id>\d+)/$',
            views.EventSepaXMLExportView.as_view(),
            name='refunds.sepa'),
]

orga_router.register('bankimportjobs', BankImportJobViewSet)
