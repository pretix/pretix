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
import importlib

from django.apps import apps
from django.urls import include, re_path
from rest_framework import routers

from .endpoints import checkout, event

storefront_orga_router = routers.DefaultRouter()
storefront_orga_router.register(r"events", event.EventViewSet)

storefront_event_router = routers.DefaultRouter()
storefront_event_router.register(r"checkouts", checkout.CheckoutViewSet)

# Force import of all plugins to give them a chance to register URLs with the router
for app in apps.get_app_configs():
    if hasattr(app, "PretixPluginMeta"):
        if importlib.util.find_spec(app.name + ".urls"):
            importlib.import_module(app.name + ".urls")

urlpatterns = [
    re_path(r"^organizers/(?P<organizer>[^/]+)/", include(storefront_orga_router.urls)),
    re_path(
        r"^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/",
        include(storefront_event_router.urls),
    ),
]
