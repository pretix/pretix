#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.urls import re_path
from pretix.api.urls import event_router

from .views import (
    LayoutEditorView,
    LayoutCreateView,
    LayoutListView,
    LayoutPreviewView,
    LayoutSetDefault,
    LayoutDelete
)
from .api import WalletLayoutViewSet

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/$',
        LayoutListView.as_view(), name='index'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/add/$',
        LayoutCreateView.as_view(), name='add'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/edit/(?P<layout>[^/]+)/$',
        LayoutEditorView.as_view(), name='edit'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/preview/$',
        LayoutPreviewView.as_view(), name='preview'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/default/(?P<layout>[^/]+)/$', # TODO
        LayoutSetDefault.as_view(), name='default'),
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/delete/(?P<layout>[^/]+)/$', # TODO
        LayoutDelete.as_view(), name='delete'),
]

event_router.register('walletlayouts', WalletLayoutViewSet)
