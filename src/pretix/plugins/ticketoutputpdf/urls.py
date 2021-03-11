from django.conf.urls import re_path

from pretix.api.urls import event_router
from pretix.plugins.ticketoutputpdf.api import (
    TicketLayoutItemViewSet, TicketLayoutViewSet,
)
from pretix.plugins.ticketoutputpdf.views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutGetDefault,
    LayoutListView, LayoutSetDefault,
)

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/$',
            LayoutListView.as_view(), name='index'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/add$',
            LayoutCreate.as_view(), name='add'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/default$',
            LayoutSetDefault.as_view(), name='default'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/default$',
            LayoutGetDefault.as_view(), name='getdefault'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/delete$',
            LayoutDelete.as_view(), name='delete'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/(?P<layout>\d+)/editor',
            LayoutEditorView.as_view(), name='edit'),
]
event_router.register('ticketlayouts', TicketLayoutViewSet)
event_router.register('ticketlayoutitems', TicketLayoutItemViewSet)
