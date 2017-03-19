from django.conf.urls import url

import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.event
import pretix.presale.views.locale
import pretix.presale.views.order
import pretix.presale.views.organizer
import pretix.presale.views.user
import pretix.presale.views.waiting

# This is not a valid Django URL configuration, as the final
# configuration is done by the pretix.multidomain package.

event_patterns = [
    url(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    url(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
    url(r'^cart/clear$', pretix.presale.views.cart.CartClear.as_view(), name='event.cart.clear'),
    url(r'^waitinglist', pretix.presale.views.waiting.WaitingView.as_view(), name='event.waitinglist'),
    url(r'^checkout/start$', pretix.presale.views.checkout.CheckoutView.as_view(), name='event.checkout.start'),
    url(r'^redeem$', pretix.presale.views.cart.RedeemView.as_view(),
        name='event.redeem'),
    url(r'^checkout/(?P<step>[^/]+)/$', pretix.presale.views.checkout.CheckoutView.as_view(),
        name='event.checkout'),
    url(r'resend/$', pretix.presale.views.user.ResendLinkView.as_view(), name='event.resend_link'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/$', pretix.presale.views.order.OrderDetails.as_view(),
        name='event.order'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice$',
        pretix.presale.views.order.OrderInvoiceCreate.as_view(),
        name='event.order.geninvoice'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel$',
        pretix.presale.views.order.OrderCancel.as_view(),
        name='event.order.cancel'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel/do$',
        pretix.presale.views.order.OrderCancelDo.as_view(),
        name='event.order.cancel.do'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/modify$',
        pretix.presale.views.order.OrderModify.as_view(),
        name='event.order.modify'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay$', pretix.presale.views.order.OrderPaymentStart.as_view(),
        name='event.order.pay'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/confirm$',
        pretix.presale.views.order.OrderPaymentConfirm.as_view(),
        name='event.order.pay.confirm'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/complete$',
        pretix.presale.views.order.OrderPaymentComplete.as_view(),
        name='event.order.pay.complete'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/change',
        pretix.presale.views.order.OrderPayChangeMethod.as_view(),
        name='event.order.pay.change'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<output>[^/]+)$',
        pretix.presale.views.order.OrderDownload.as_view(),
        name='event.order.download.combined'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/(?P<output>[^/]+)$',
        pretix.presale.views.order.OrderDownload.as_view(),
        name='event.order.download'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/invoice/(?P<invoice>[0-9]+)$',
        pretix.presale.views.order.InvoiceDownload.as_view(),
        name='event.invoice.download'),
    url(r'^ical$',
        pretix.presale.views.event.EventIcalDownload.as_view(),
        name='event.ical.download'),
    url(r'^auth/$', pretix.presale.views.event.EventAuth.as_view(), name='event.auth'),
    url(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
]

organizer_patterns = [
    url(r'^$', pretix.presale.views.organizer.OrganizerIndex.as_view(), name='organizer.index'),
]

locale_patterns = [
    url(r'^locale/set$', pretix.presale.views.locale.LocaleSet.as_view(), name='locale.set'),
]
