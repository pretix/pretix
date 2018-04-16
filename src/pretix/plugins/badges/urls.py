from django.conf.urls import url

from .views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutListView, LayoutUpdate,
)

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/$',
        LayoutListView.as_view(), name='index'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/add$',
        LayoutCreate.as_view(), name='add'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/$',
        LayoutUpdate.as_view(), name='edit'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/delete$',
        LayoutDelete.as_view(), name='delete'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/pdfeditor/',
        LayoutEditorView.as_view(), name='editor'),
]
