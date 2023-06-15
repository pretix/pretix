#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from pretix.plugins.ticketoutputpdf.api import (
    TicketLayoutItemViewSet, TicketLayoutViewSet,
)
from pretix.plugins.ticketoutputpdf.views import (
    LayoutCreate, LayoutDelete, LayoutEditorView, LayoutGetDefault,
    LayoutListView, LayoutSetDefault, OrderPrintDo,
)

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/pdfoutput/print$',
            OrderPrintDo.as_view(), name='print'),
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
