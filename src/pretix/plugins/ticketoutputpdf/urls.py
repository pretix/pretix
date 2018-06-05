from django.conf.urls import url

from pretix.plugins.ticketoutputpdf.views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutListView,
    LayoutSetDefault,
)

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/$',
        LayoutListView.as_view(), name='index'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/add$',
        LayoutCreate.as_view(), name='add'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/default$',
        LayoutSetDefault.as_view(), name='default'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/delete$',
        LayoutDelete.as_view(), name='delete'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/editor',
        LayoutEditorView.as_view(), name='edit'),
]
