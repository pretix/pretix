import importlib

from django.apps import apps
from django.conf.urls import include, re_path
from rest_framework import routers

from pretix.api.views import cart

from .views import (
    checkin, device, event, exporters, item, oauth, order, organizer, upload,
    user, version, voucher, waitinglist, webhooks,
)

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)

orga_router = routers.DefaultRouter()
orga_router.register(r'events', event.EventViewSet)
orga_router.register(r'subevents', event.SubEventViewSet)
orga_router.register(r'webhooks', webhooks.WebHookViewSet)
orga_router.register(r'seatingplans', organizer.SeatingPlanViewSet)
orga_router.register(r'giftcards', organizer.GiftCardViewSet)
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
event_router.register(r'quotas', item.QuotaViewSet)
event_router.register(r'vouchers', voucher.VoucherViewSet)
event_router.register(r'orders', order.OrderViewSet)
event_router.register(r'orderpositions', order.OrderPositionViewSet)
event_router.register(r'invoices', order.InvoiceViewSet)
event_router.register(r'revokedsecrets', order.RevokedSecretViewSet, basename='revokedsecrets')
event_router.register(r'taxrules', event.TaxRuleViewSet)
event_router.register(r'waitinglistentries', waitinglist.WaitingListViewSet)
event_router.register(r'checkinlists', checkin.CheckinListViewSet)
event_router.register(r'cartpositions', cart.CartPositionViewSet)
event_router.register(r'exporters', exporters.EventExportersViewSet, basename='exporters')

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
    re_path(r'^organizers/(?P<organizer>[^/]+)/settings/$', organizer.OrganizerSettingsView.as_view(),
            name="organizer.settings"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/giftcards/(?P<giftcard>[^/]+)/', include(giftcard_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/settings/$', event.EventSettingsView.as_view(),
            name="event.settings"),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/', include(event_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/teams/(?P<team>[^/]+)/', include(team_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/items/(?P<item>[^/]+)/',
            include(item_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/questions/(?P<question>[^/]+)/',
            include(question_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/checkinlists/(?P<list>[^/]+)/',
            include(checkinlist_router.urls)),
    re_path(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/orders/(?P<order>[^/]+)/',
            include(order_router.urls)),
    re_path(r"^oauth/authorize$", oauth.AuthorizationView.as_view(), name="authorize"),
    re_path(r"^oauth/token$", oauth.TokenView.as_view(), name="token"),
    re_path(r"^oauth/revoke_token$", oauth.RevokeTokenView.as_view(), name="revoke-token"),
    re_path(r"^device/initialize$", device.InitializeView.as_view(), name="device.initialize"),
    re_path(r"^device/update$", device.UpdateView.as_view(), name="device.update"),
    re_path(r"^device/roll$", device.RollKeyView.as_view(), name="device.roll"),
    re_path(r"^device/revoke$", device.RevokeKeyView.as_view(), name="device.revoke"),
    re_path(r"^device/eventselection$", device.EventSelectionView.as_view(), name="device.eventselection"),
    re_path(r"^upload$", upload.UploadView.as_view(), name="upload"),
    re_path(r"^me$", user.MeView.as_view(), name="user.me"),
    re_path(r"^version$", version.VersionView.as_view(), name="version"),
]
