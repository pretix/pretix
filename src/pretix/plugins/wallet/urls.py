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
from pretix.plugins.wallet.views.google import CallbackView
import pretix

from .api import WalletLayoutViewSet
from .views.apple import (
    DeviceGetUpdatablePassesView,
    DeviceRegistrationView,
    GetPassView,
    LogView,
)
from .views.control import (
    LayoutCreateView,
    LayoutDelete,
    LayoutEditorView,
    LayoutListView,
    LayoutPreviewView,
    LayoutSetDefault,
    WalletGetView
)
from .views.presale import PresaleWalletGetPass, PresaleWalletGetPassPosition

urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/$",
        LayoutListView.as_view(),
        name="index",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/add/$",
        LayoutCreateView.as_view(),
        name="add",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/edit/(?P<layout>[^/]+)/$",
        LayoutEditorView.as_view(),
        name="edit",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/preview/$",
        LayoutPreviewView.as_view(),
        name="preview",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/default/(?P<layout>[^/]+)/$",
        LayoutSetDefault.as_view(),
        name="default",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/wallet/delete/(?P<layout>[^/]+)/$",
        LayoutDelete.as_view(),
        name="delete",
    ),
    re_path(
        # TODO(wallet): actually provide this view
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/orders/(?P<code>[0-9A-Z]+)/wallet/(?P<position>\d+)/(?P<platform>[^/]+)/$",
        WalletGetView.as_view(),
        name="event.order.wallet.get",
    ),
]

event_patterns = [
    re_path(
        r"_wallet/apple/v1/devices/(?P<device_library_identifier>[^/]+)/registrations/(?P<pass_type_identifier>[^/]+)/(?P<serial_number>[^/]+)$",
        DeviceRegistrationView.as_view(),
        name="apple_register",
    ),
    re_path(
        r"_wallet/apple/v1/devices/(?P<device_library_identifier>[^/]+)/registrations/(?P<pass_type_identifier>[^/]+)$",
        DeviceGetUpdatablePassesView.as_view(),
        name="apple_get-updatable",
    ),
    re_path(
        r"_wallet/apple/v1/passes/(?P<pass_type_identifier>[^/]+)/(?P<serial_number>[^/]+)$",
        GetPassView.as_view(),
        name="apple_get-pass",
    ),
    re_path(
        r"_wallet/apple/v1/log$",
        LogView.as_view(),
        name="apple_log",
    ),
    re_path(
        r"_wallet/google/callback$",
        CallbackView.as_view(),
        name="google_webhook",
    ),
    # TODO(wallet): actually provide these views
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/(?P<platform>[^/]+)$",
        PresaleWalletGetPass.as_view(),
        name="presale_event.order.wallet.get",
    ),
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<platform>[^/]+)$",
        PresaleWalletGetPass.as_view(),
        name="presale_event.order.wallet.get.combined",
    ),
    re_path(
        r"^ticket/(?P<order>[^/]+)/(?P<position>\d+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<pid>[0-9]+)/(?P<platform>[^/]+)$",
        PresaleWalletGetPassPosition.as_view(),
        name="presale_event.order.position.wallet.get",
    ),
]

event_router.register("walletlayouts", WalletLayoutViewSet)
