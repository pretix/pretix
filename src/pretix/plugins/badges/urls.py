from django.conf.urls import url

from pretix.api.urls import event_router
from pretix.plugins.badges.api import BadgeLayoutViewSet

from .views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutListView,
    LayoutSetDefault, OrderPrintDo,
)

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/$',
        LayoutListView.as_view(), name='index'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/print$',
        OrderPrintDo.as_view(), name='print'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/add$',
        LayoutCreate.as_view(), name='add'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/default$',
        LayoutSetDefault.as_view(), name='default'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/delete$',
        LayoutDelete.as_view(), name='delete'),
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/editor',
        LayoutEditorView.as_view(), name='edit'),
]
event_router.register('badgelayouts', BadgeLayoutViewSet)
