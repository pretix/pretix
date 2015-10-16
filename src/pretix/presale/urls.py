from django.conf.urls import include, url

import pretix.presale.views.cart
import pretix.presale.views.checkout
import pretix.presale.views.event
import pretix.presale.views.locale
import pretix.presale.views.order

eventurls = [
    url(r'^cart/add$', pretix.presale.views.cart.CartAdd.as_view(), name='event.cart.add'),
    url(r'^cart/remove$', pretix.presale.views.cart.CartRemove.as_view(), name='event.cart.remove'),
    url(r'^checkout/start$', pretix.presale.views.checkout.CheckoutView.as_view(), name='event.checkout.start'),
    url(r'^checkout/(?P<step>[^/]+)/$', pretix.presale.views.checkout.CheckoutView.as_view(),
        name='event.checkout'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/$', pretix.presale.views.order.OrderDetails.as_view(),
        name='event.order'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/cancel$',
        pretix.presale.views.order.OrderCancel.as_view(),
        name='event.order.cancel'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/modify$',
        pretix.presale.views.order.OrderModify.as_view(),
        name='event.order.modify'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay$', pretix.presale.views.order.OrderPay.as_view(),
        name='event.order.pay'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/confirm$',
        pretix.presale.views.order.OrderPayDo.as_view(),
        name='event.order.pay.confirm'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/pay/complete$',
        pretix.presale.views.order.OrderPayComplete.as_view(),
        name='event.order.pay.complete'),
    url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<output>[^/]+)$',
        pretix.presale.views.order.OrderDownload.as_view(),
        name='event.order.download'),
    url(r'^$', pretix.presale.views.event.EventIndex.as_view(), name='event.index'),
]

urlpatterns = [
    url(r'^locale/set$', pretix.presale.views.locale.LocaleSet.as_view(), name='locale.set'),
    url(r'^(?P<event>[^/]+)/', include(eventurls)),
    url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/', include(eventurls)),
]
