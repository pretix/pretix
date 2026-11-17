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

from .views import (
    DeviceGetUpdatablePassesView, DeviceRegistrationView,
    DownloadCombinedPassView, DownloadPassView, GetPassView, LogView,
)

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
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/wallet/apple/download/(?P<position>[0-9]+)/$",
        DownloadPassView.as_view(),
        name="download",
    ),
    re_path(
        r"^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/wallet/apple/download/$",
        DownloadCombinedPassView.as_view(),
        name="download_combined",
    ),
]
