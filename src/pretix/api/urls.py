import importlib

from django.apps import apps
from django.conf.urls import include, url
from rest_framework import routers

from pretix.api.views import cart

from .views import (
    checkin, device, event, item, oauth, order, organizer, user, voucher,
    waitinglist, webhooks,
)

router = routers.DefaultRouter()
router.register(r'organizers', organizer.OrganizerViewSet)

orga_router = routers.DefaultRouter()
orga_router.register(r'events', event.EventViewSet)
orga_router.register(r'subevents', event.SubEventViewSet)
orga_router.register(r'webhooks', webhooks.WebHookViewSet)

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
event_router.register(r'taxrules', event.TaxRuleViewSet)
event_router.register(r'waitinglistentries', waitinglist.WaitingListViewSet)
event_router.register(r'checkinlists', checkin.CheckinListViewSet)
event_router.register(r'cartpositions', cart.CartPositionViewSet)

checkinlist_router = routers.DefaultRouter()
checkinlist_router.register(r'positions', checkin.CheckinListPositionViewSet)

question_router = routers.DefaultRouter()
question_router.register(r'options', item.QuestionOptionViewSet)

item_router = routers.DefaultRouter()
item_router.register(r'variations', item.ItemVariationViewSet)
item_router.register(r'addons', item.ItemAddOnViewSet)

order_router = routers.DefaultRouter()
order_router.register(r'payments', order.PaymentViewSet)
order_router.register(r'refunds', order.RefundViewSet)

# Force import of all plugins to give them a chance to register URLs with the router
for app in apps.get_app_configs():
    if hasattr(app, 'PretixPluginMeta'):
        if importlib.util.find_spec(app.name + '.urls'):
            importlib.import_module(app.name + '.urls')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/', include(orga_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/', include(event_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/items/(?P<item>[^/]+)/', include(item_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/questions/(?P<question>[^/]+)/',
        include(question_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/checkinlists/(?P<list>[^/]+)/',
        include(checkinlist_router.urls)),
    url(r'^organizers/(?P<organizer>[^/]+)/events/(?P<event>[^/]+)/orders/(?P<order>[^/]+)/', include(order_router.urls)),
    url(r"^oauth/authorize$", oauth.AuthorizationView.as_view(), name="authorize"),
    url(r"^oauth/token$", oauth.TokenView.as_view(), name="token"),
    url(r"^oauth/revoke_token$", oauth.RevokeTokenView.as_view(), name="revoke-token"),
    url(r"^device/initialize$", device.InitializeView.as_view(), name="device.initialize"),
    url(r"^device/update$", device.UpdateView.as_view(), name="device.update"),
    url(r"^device/roll$", device.RollKeyView.as_view(), name="device.roll"),
    url(r"^device/revoke$", device.RevokeKeyView.as_view(), name="device.revoke"),
    url(r"^me$", user.MeView.as_view(), name="user.me"),
]
