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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Ture Gjørup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import importlib

from django.apps import apps
from django.urls import include, re_path
from rest_framework import routers

from pretix.api.views import cart

from .views import (
    checkin, device, discount, event, exporters, idempotency, item, media,
    oauth, order, organizer, shredders, upload, user, version, voucher,
    waitinglist, webhooks,
)

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)

orga_router = routers.DefaultRouter()
orga_router.register(r'events', event.EventViewSet)
orga_router.register(r'subevents', event.SubEventViewSet)
orga_router.register(r'webhooks', webhooks.WebHookViewSet)
orga_router.register(r'seatingplans', organizer.SeatingPlanViewSet)
orga_router.register(r'giftcards', organizer.GiftCardViewSet)
orga_router.register(r'customers', organizer.CustomerViewSet)
orga_router.register(r'memberships', organizer.MembershipViewSet)
orga_router.register(r'membershiptypes', organizer.MembershipTypeViewSet)
orga_router.register(r'reusablemedia', media.ReusableMediaViewSet)
orga_router.register(r'teams', organizer.TeamViewSet)
orga_router.register(r'devices', organizer.DeviceViewSet)
orga_router.register(r'exporters', exporters.OrganizerExportersViewSet, basename='exporters')

team_router = routers.DefaultRouter()
team_router.register(r'members', organizer.TeamMemberViewSet)
team_router.register(r'invites', organizer.TeamInviteViewSet)
team_router.register(r'tokens', organizer.TeamAPITokenViewSet)

event_router = routers.DefaultRouter()
event_router.register(r'subevents', event.SubEventViewSet)
event_router.register(r'clone', event.CloneEventViewSet)
event_router.register(r'items', item.ItemViewSet)
event_router.register(r'categories', item.ItemCategoryViewSet)
event_router.register(r'questions', item.QuestionViewSet)
event_router.register(r'discounts', discount.DiscountViewSet)
event_router.register(r'quotas', item.QuotaViewSet)
event_router.register(r'vouchers', voucher.VoucherViewSet)
event_router.register(r'orders', order.OrderViewSet)
event_router.register(r'orderpositions', order.OrderPositionViewSet)
event_router.register(r'invoices', order.InvoiceViewSet)
event_router.register(r'revokedsecrets', order.RevokedSecretViewSet, basename='revokedsecrets')
event_router.register(r'blockedsecrets', order.BlockedSecretViewSet, basename='blockedsecrets')
event_router.register(r'taxrules', event.TaxRuleViewSet)
event_router.register(r'waitinglistentries', waitinglist.WaitingListViewSet)
event_router.register(r'checkinlists', checkin.CheckinListViewSet)
event_router.register(r'cartpositions', cart.CartPositionViewSet)
event_router.register(r'exporters', exporters.EventExportersViewSet, basename='exporters')
event_router.register(r'shredders', shredders.EventShreddersViewSet, basename='shredders')
event_router.register(r'item_meta_properties', event.ItemMetaPropertiesViewSet)

checkinlist_router = routers.DefaultRouter()
checkinlist_router.register(r'positions', checkin.CheckinListPositionViewSet, basename='checkinlistpos')

question_router = routers.DefaultRouter()
question_router.register(r'options', item.QuestionOptionViewSet)

item_router = routers.DefaultRouter()
item_router.register(r'variations', item.ItemVariationViewSet)
item_router.register(r'addons', item.ItemAddOnViewSet)
item_router.register(r'bundles', item.ItemBundleViewSet)

order_router = routers.DefaultRouter()
order_router.register(r'payments', order.PaymentViewSet)
order_router.register(r'refunds', order.RefundViewSet)

giftcard_router = routers.DefaultRouter()
giftcard_router.register(r'transactions', organizer.GiftCardTransactionViewSet)

# Force import of all plugins to give them a chance to register URLs with the router
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            importlib.import_module(app.name + '.urls')

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/', include(orga_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/checkinrpc/redeem/$', checkin.CheckinRPCRedeemView.as_view(),
            name="checkinrpc.redeem"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/checkinrpc/search/$', checkin.CheckinRPCSearchView.as_view(),
            name="checkinrpc.search"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/settings/$', organizer.OrganizerSettingsView.as_view(),
            name="organizer.settings"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/giftcards/(?P<giftcard>[^/]+)/', include(giftcard_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/settings/$', event.EventSettingsView.as_view(),
            name="event.settings"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/', include(event_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/teams/(?P<team>[^/]+)/', include(team_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/items/(?P<item>[^/]+)/', include(item_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/questions/(?P<question>[^/]+)/',
            include(question_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/checkinlists/(?P<list>[^/]+)/',
            include(checkinlist_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/orders/(?P<order>[^/]+)/', include(order_router.urls)),
    re_path(r"^oauth/authorize$", oauth.AuthorizationView.as_view(), name="authorize"),
    re_path(r"^oauth/token$", oauth.TokenView.as_view(), name="token"),
    re_path(r"^oauth/revoke_token$", oauth.RevokeTokenView.as_view(), name="revoke-token"),
    re_path(r"^device/initialize$", device.InitializeView.as_view(), name="device.initialize"),
    re_path(r"^device/update$", device.UpdateView.as_view(), name="device.update"),
    re_path(r"^device/roll$", device.RollKeyView.as_view(), name="device.roll"),
    re_path(r"^device/revoke$", device.RevokeKeyView.as_view(), name="device.revoke"),
    re_path(r"^device/info$", device.InfoView.as_view(), name="device.info"),
    re_path(r"^device/eventselection$", device.EventSelectionView.as_view(), name="device.eventselection"),
    re_path(r"^idempotency_query$", idempotency.IdempotencyQueryView.as_view(), name="idempotency.query"),
    re_path(r"^upload$", upload.UploadView.as_view(), name="upload"),
    re_path(r"^me$", user.MeView.as_view(), name="user.me"),
    re_path(r"^version$", version.VersionView.as_view(), name="version"),
]
