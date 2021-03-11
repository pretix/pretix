from django.conf.urls import re_path

from pretix.api.urls import event_router
from pretix.plugins.badges.api import BadgeItemViewSet, BadgeLayoutViewSet

from .views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutListView,
    LayoutSetDefault, OrderPrintDo,
)

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/$',
            LayoutListView.as_view(), name='index'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/print$',
            OrderPrintDo.as_view(), name='print'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/add$',
            LayoutCreate.as_view(), name='add'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/default$',
            LayoutSetDefault.as_view(), name='default'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/delete$',
            LayoutDelete.as_view(), name='delete'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/badges/(?P<layout>\d+)/editor',
            LayoutEditorView.as_view(), name='edit'),
]
event_router.register('badgelayouts', BadgeLayoutViewSet)
event_router.register('badgeitems', BadgeItemViewSet)
